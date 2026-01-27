"""
实时推理服务 - 运行在 mt conda 环境中
参考 virtual-tutor 的 musereal.py

架构：
- 独立进程，通过 subprocess 启动
- 使用 threading.Thread 进行实时推理
- 通过 HTTP API 接收音频，返回视频帧流
"""

import sys
import os
import logging
import threading
import queue
from queue import Queue, Empty
import time
import base64
import tempfile
import asyncio
from typing import Optional, AsyncGenerator
import argparse

import torch
import numpy as np
import cv2
import pickle
from pathlib import Path

# 添加 MuseTalk 到路径
MUSETALK_BASE = os.environ.get('MUSETALK_BASE', '/workspace/MuseTalk')
sys.path.insert(0, MUSETALK_BASE)

from musetalk.utils.utils import load_all_model
from musetalk.whisper.audio2feature import Audio2Feature
from musetalk.utils.blending import get_image

# FastAPI
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('RealtimeInference')


class AudioRequest(BaseModel):
    """音频请求"""
    audio_data: str  # base64编码的音频
    fps: int = 25


class RealtimeInferenceEngine:
    """
    实时推理引擎 - 使用 threading.Thread

    参考 virtual-tutor/lip-sync/musereal.py
    """

    def __init__(self, avatar_id: str, avatar_path: str, batch_size: int = 8):
        self.avatar_id = avatar_id
        self.avatar_path = avatar_path
        self.batch_size = batch_size

        # 队列
        self.audio_feat_queue = Queue(maxsize=2)
        self.res_frame_queue = Queue(maxsize=batch_size * 2)

        # 控制事件
        self.render_event = threading.Event()

        # 推理线程
        self.inference_thread: Optional[threading.Thread] = None

        # 模型
        self.vae = None
        self.unet = None
        self.pe = None
        self.timesteps = None
        self.audio_processor = None

        # Avatar 数据
        self.coord_list_cycle = None
        self.frame_list_cycle = None
        self.mask_list_cycle = None
        self.mask_coords_list_cycle = None
        self.input_latent_list_cycle = None

        logger.info(f"[{avatar_id}] Engine initialized")

    def start(self):
        """启动推理线程"""
        if self.inference_thread is not None:
            logger.warning(f"[{self.avatar_id}] Engine already started")
            return

        logger.info(f"[{self.avatar_id}] Loading models...")

        # 切换到 MuseTalk 目录（模型路径是相对路径）
        original_cwd = os.getcwd()
        os.chdir(MUSETALK_BASE)

        try:
            # 1. 加载 MuseTalk 模型
            vae, unet, pe = load_all_model()

            # 2. 创建 audio processor
            # whisper 使用模型名称，不是路径
            audio_processor = Audio2Feature(
                whisper_model_type="tiny",
                model_path="tiny"  # 直接使用模型名称
            )

            # 转换为 half 精度
            pe = pe.half()
            vae.vae = vae.vae.half()
            unet.model = unet.model.half()

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            timesteps = torch.tensor([0], device=device)

            self.vae = vae
            self.unet = unet
            self.pe = pe
            self.timesteps = timesteps
            self.audio_processor = audio_processor

            logger.info(f"[{self.avatar_id}] Models loaded on {device}")

            # 2. 加载 Avatar 数据
            self._load_avatar_data()

            # 3. 启动推理线程
            self.render_event.set()
            self.inference_thread = threading.Thread(
                target=self._inference_loop,
                daemon=True
            )
            self.inference_thread.start()

            logger.info(f"[{self.avatar_id}] Inference thread started")

        finally:
            # 恢复原工作目录
            os.chdir(original_cwd)

    def _load_avatar_data(self):
        """加载 Avatar 数据"""
        # 加载 latents
        latents_path = os.path.join(self.avatar_path, "latents.pt")
        if not os.path.exists(latents_path):
            raise FileNotFoundError(f"Latents not found: {latents_path}")
        self.input_latent_list_cycle = torch.load(latents_path)

        # 加载 coords
        coords_path = os.path.join(self.avatar_path, "coords.pkl")
        if not os.path.exists(coords_path):
            raise FileNotFoundError(f"Coords not found: {coords_path}")
        with open(coords_path, 'rb') as f:
            self.coord_list_cycle = pickle.load(f)

        # 加载原始图像
        full_imgs_path = os.path.join(self.avatar_path, "full_imgs")
        if not os.path.exists(full_imgs_path):
            raise FileNotFoundError(f"full_imgs not found: {full_imgs_path}")

        img_list = sorted(
            Path(full_imgs_path).glob("*.[jpJP][pnPN]*[gG]"),
            key=lambda x: int(x.stem)
        )
        self.frame_list_cycle = [cv2.imread(str(p)) for p in img_list]

        # 加载 mask
        mask_path = os.path.join(self.avatar_path, "mask")
        mask_coords_path = os.path.join(self.avatar_path, "mask_coords.pkl")

        if not os.path.exists(mask_coords_path):
            raise FileNotFoundError(f"mask_coords not found: {mask_coords_path}")

        with open(mask_coords_path, 'rb') as f:
            self.mask_coords_list_cycle = pickle.load(f)

        mask_list = sorted(
            Path(mask_path).glob("*.[jpJP][pnPN]*[gG]"),
            key=lambda x: int(x.stem)
        )
        self.mask_list_cycle = [cv2.imread(str(p)) for p in mask_list]

        logger.info(f"[{self.avatar_id}] Avatar data loaded: {len(self.coord_list_cycle)} frames")

    def _mirror_index(self, size: int, index: int) -> int:
        """镜像索引"""
        turn = index // size
        res = index % size
        return res if turn % 2 == 0 else size - res - 1

    @torch.no_grad()
    def _inference_loop(self):
        """
        推理循环（在 Thread 中运行）

        参考: virtual-tutor/lip-sync/musereal.py inference()
        """
        length = len(self.coord_list_cycle)
        index = 0
        count = 0
        counttime = 0

        logger.info(f"[{self.avatar_id}] Inference loop started")

        while self.render_event.is_set():
            try:
                # 从队列获取音频特征（1秒超时）
                whisper_chunks = self.audio_feat_queue.get(timeout=1)
            except Empty:
                continue

            starttime = time.perf_counter()

            # 批量推理
            whisper_batch = np.stack(whisper_chunks)
            latent_batch = []
            for i in range(self.batch_size):
                idx = self._mirror_index(length, index + i)
                latent = self.input_latent_list_cycle[idx]
                latent_batch.append(latent)

            latent_batch = torch.cat(latent_batch, dim=0)

            # 准备音频特征
            audio_feature_batch = torch.from_numpy(whisper_batch)
            audio_feature_batch = audio_feature_batch.to(
                device=self.unet.device,
                dtype=self.unet.model.dtype
            )
            audio_feature_batch = self.pe(audio_feature_batch)
            latent_batch = latent_batch.to(dtype=self.unet.model.dtype)

            # UNet 推理
            pred_latents = self.unet.model(
                latent_batch,
                self.timesteps,
                encoder_hidden_states=audio_feature_batch
            ).sample

            # VAE 解码
            recon = self.vae.decode_latents(pred_latents)

            elapsed = time.perf_counter() - starttime
            counttime += elapsed
            count += self.batch_size

            if count >= 100:
                logger.info(f"[{self.avatar_id}] Avg infer FPS: {count/counttime:.2f}")
                count = 0
                counttime = 0

            # 混合生成的帧
            for i, res_frame in enumerate(recon):
                idx = self._mirror_index(length, index)

                # 帧混合
                bbox = self.coord_list_cycle[idx]
                ori_frame = self.frame_list_cycle[idx].copy()

                try:
                    res_frame_np = res_frame.cpu().numpy().transpose(1, 2, 0)
                    res_frame_np = (res_frame_np * 255).astype(np.uint8)
                    res_frame_np = cv2.cvtColor(res_frame_np, cv2.COLOR_RGB2BGR)

                    combined_frame = get_image(
                        res_frame_np,
                        ori_frame,
                        bbox,
                        self.mask_list_cycle[idx],
                        self.mask_coords_list_cycle[idx]
                    )
                except Exception as e:
                    logger.error(f"[{self.avatar_id}] Frame blending error: {e}")
                    combined_frame = ori_frame

                # 立即放入帧队列 ⚡
                self.res_frame_queue.put((combined_frame, idx))
                index += 1

        logger.info(f"[{self.avatar_id}] Inference loop stopped")

    async def generate_frames(
        self,
        audio_data: str,
        fps: int = 25
    ) -> AsyncGenerator[bytes, None]:
        """
        生成帧流（异步）

        流程：
        1. 提取音频特征
        2. 放入队列
        3. 从帧队列实时读取并yield
        """
        import subprocess
        
        # 1. 解码音频
        audio_bytes = base64.b64decode(audio_data)

        # 先保存原始音频（可能是 MP3 或 WAV）
        with tempfile.NamedTemporaryFile(suffix='.tmp', delete=False) as f:
            f.write(audio_bytes)
            temp_audio_path = f.name

        # 使用 ffmpeg 转换为 16kHz mono WAV（MuseTalk 要求的格式）
        audio_path = temp_audio_path.replace('.tmp', '.wav')
        try:
            cmd = [
                'ffmpeg', '-y', '-i', temp_audio_path,
                '-ar', '16000',  # 16kHz 采样率
                '-ac', '1',      # 单声道
                '-f', 'wav',     # WAV 格式
                audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"[{self.avatar_id}] FFmpeg conversion failed: {result.stderr}")
                raise RuntimeError(f"Audio conversion failed: {result.stderr}")
            logger.info(f"[{self.avatar_id}] ✅ Audio converted to WAV: {audio_path}")
        finally:
            # 删除临时文件
            try:
                os.unlink(temp_audio_path)
            except:
                pass

        try:
            # 2. 提取 Whisper 特征
            logger.info(f"[{self.avatar_id}] Extracting audio features...")

            loop = asyncio.get_event_loop()

            def extract_features():
                whisper_feature = self.audio_processor.audio2feat(audio_path)
                return self.audio_processor.feature2chunks(
                    feature_array=whisper_feature,
                    fps=fps / 2,
                    batch_size=self.batch_size,
                    start=0
                )

            whisper_chunks = await loop.run_in_executor(None, extract_features)

            logger.info(f"[{self.avatar_id}] Extracted {len(whisper_chunks)} chunks")

            # 3. 放入音频队列
            for chunk in whisper_chunks:
                self.audio_feat_queue.put(chunk)

            # 4. 从帧队列读取并 yield
            total_frames = len(whisper_chunks) * self.batch_size
            frame_count = 0
            first_frame_time = None

            while frame_count < total_frames:
                try:
                    frame, idx = await loop.run_in_executor(
                        None,
                        lambda: self.res_frame_queue.get(timeout=2)
                    )

                    if frame_count == 0:
                        first_frame_time = time.time()
                        logger.info(f"[{self.avatar_id}] ⚡ First frame generated!")

                    # 编码为 JPEG
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    frame_bytes = buffer.tobytes()

                    yield frame_bytes
                    frame_count += 1

                except Empty:
                    await asyncio.sleep(0.01)
                    continue

            if first_frame_time:
                total_time = time.time() - first_frame_time
                logger.info(
                    f"[{self.avatar_id}] Generated {frame_count} frames "
                    f"in {total_time:.2f}s (avg {frame_count/total_time:.2f} fps)"
                )

        finally:
            os.unlink(audio_path)

    def stop(self):
        """停止推理线程"""
        self.render_event.clear()
        if self.inference_thread:
            self.inference_thread.join(timeout=5)
        logger.info(f"[{self.avatar_id}] Engine stopped")


# 全局引擎实例
_engine: Optional[RealtimeInferenceEngine] = None

# FastAPI 应用
app = FastAPI(title="MuseTalk Realtime Inference Service")


@app.on_event("startup")
async def startup():
    """启动时初始化引擎"""
    global _engine

    avatar_id = os.environ.get('AVATAR_ID')
    avatar_path = os.environ.get('AVATAR_PATH')
    batch_size = int(os.environ.get('BATCH_SIZE', '8'))

    if not avatar_id or not avatar_path:
        raise RuntimeError("AVATAR_ID and AVATAR_PATH must be set")

    logger.info(f"Initializing engine for avatar: {avatar_id}")
    _engine = RealtimeInferenceEngine(avatar_id, avatar_path, batch_size)
    _engine.start()
    logger.info("Engine started successfully")


@app.on_event("shutdown")
async def shutdown():
    """关闭时停止引擎"""
    global _engine
    if _engine:
        _engine.stop()


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "avatar_id": _engine.avatar_id if _engine else None}


@app.post("/generate")
async def generate(request: AudioRequest):
    """
    生成视频帧流

    返回：multipart/x-mixed-replace 流
    """
    if not _engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    async def frame_generator():
        """帧生成器"""
        boundary = "frame"

        async for frame_bytes in _engine.generate_frames(request.audio_data, request.fps):
            yield (
                b'--' + boundary.encode() + b'\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                frame_bytes + b'\r\n'
            )

    return StreamingResponse(
        frame_generator(),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )


def main():
    parser = argparse.ArgumentParser(description='MuseTalk Realtime Inference Service')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Host to bind')
    parser.add_argument('--port', type=int, default=9100, help='Port to bind')
    parser.add_argument('--avatar-id', type=str, required=True, help='Avatar ID')
    parser.add_argument('--avatar-path', type=str, required=True, help='Avatar data path')
    parser.add_argument('--batch-size', type=int, default=8, help='Batch size')

    args = parser.parse_args()

    # 设置环境变量
    os.environ['AVATAR_ID'] = args.avatar_id
    os.environ['AVATAR_PATH'] = args.avatar_path
    os.environ['BATCH_SIZE'] = str(args.batch_size)

    # 启动服务
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info"
    )


if __name__ == '__main__':
    main()
