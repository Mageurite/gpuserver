"""
MuseTalk 实时推理引擎 - 完全基于 virtual-tutor 的实现

参考: /workspace/virtual-tutor/lip-sync/musereal.py

关键架构:
- 使用 threading.Thread（不是 multiprocessing.Process）
- 在主进程中加载模型
- 通过 Queue 传递音频特征和视频帧
"""

import logging
import sys
import os
import time
from typing import Optional, AsyncIterator
import asyncio
from queue import Queue, Empty
from threading import Thread, Event
import pickle
from pathlib import Path

import torch
import numpy as np
import cv2

# 添加 MuseTalk 路径到 sys.path（如果还没有）
MUSETALK_BASE = os.getenv('MUSETALK_BASE', '/workspace/MuseTalk')
if MUSETALK_BASE not in sys.path:
    sys.path.insert(0, MUSETALK_BASE)

logger = logging.getLogger(__name__)


def mirror_index(size: int, index: int) -> int:
    """镜像索引"""
    turn = index // size
    res = index % size
    return res if turn % 2 == 0 else size - res - 1


@torch.no_grad()
def inference_loop(
    render_event: Event,
    batch_size: int,
    input_latent_list_cycle,
    coord_list_cycle,
    frame_list_cycle,
    mask_list_cycle,
    mask_coords_list_cycle,
    audio_feat_queue: Queue,
    res_frame_queue: Queue,
    vae, unet, pe, timesteps
):
    """
    推理循环（在 Thread 中运行）

    参考: virtual-tutor/lip-sync/musereal.py inference()
    """
    from musetalk.utils.blending import get_image_blending

    length = len(coord_list_cycle)
    index = 0
    count = 0
    counttime = 0

    logger.info('Inference thread started')

    while render_event.is_set():
        try:
            # 从队列获取音频特征（1秒超时）
            whisper_chunks = audio_feat_queue.get(timeout=1)
        except Empty:
            # 队列为空，短暂休眠避免 CPU 100%
            time.sleep(0.1)
            continue

        starttime = time.perf_counter()

        # 批量推理
        whisper_batch = np.stack(whisper_chunks)
        latent_batch = []
        for i in range(batch_size):
            idx = mirror_index(length, index + i)
            latent = input_latent_list_cycle[idx]
            latent_batch.append(latent)

        latent_batch = torch.cat(latent_batch, dim=0)

        # 准备音频特征
        audio_feature_batch = torch.from_numpy(whisper_batch)
        audio_feature_batch = audio_feature_batch.to(
            device=unet.device,
            dtype=unet.model.dtype
        )
        audio_feature_batch = pe(audio_feature_batch)
        latent_batch = latent_batch.to(dtype=unet.model.dtype)

        # UNet 推理
        pred_latents = unet.model(
            latent_batch,
            timesteps,
            encoder_hidden_states=audio_feature_batch
        ).sample

        # VAE 解码
        recon = vae.decode_latents(pred_latents)

        # 调试: 检查 recon 的类型和形状
        logger.info(f"recon type: {type(recon)}, shape: {recon.shape if hasattr(recon, 'shape') else 'N/A'}")

        elapsed = time.perf_counter() - starttime
        counttime += elapsed
        count += batch_size

        if count >= 100:
            logger.info(f"Avg infer FPS: {count/counttime:.2f}")
            count = 0
            counttime = 0

        # 混合生成的帧
        for i, res_frame in enumerate(recon):
            idx = mirror_index(length, index)

            # 调试: 检查 res_frame 的类型和形状
            if i == 0:  # 只打印第一帧的信息
                logger.info(f"res_frame[{i}] type: {type(res_frame)}, shape: {res_frame.shape if hasattr(res_frame, 'shape') else 'N/A'}")
                logger.info(f"res_frame[{i}] dtype: {res_frame.dtype}, min: {res_frame.min()}, max: {res_frame.max()}")

            # 帧混合
            bbox = coord_list_cycle[idx]
            ori_frame = frame_list_cycle[idx].copy()

            try:
                # VAE decode_latents 已经返回 uint8 BGR 格式（见 vae.py:106-107）
                # 不需要任何转换，直接使用
                res_frame_np = res_frame  # 直接使用 VAE 输出
                
                # 调试：检查 res_frame 的值
                if index == 0:
                    logger.info(f"[Debug] res_frame from VAE: dtype={res_frame_np.dtype}, min={res_frame_np.min()}, max={res_frame_np.max()}")

                # CRITICAL: Resize face to bbox size before blending
                # 参考 virtual-tutor/lip-sync/musereal.py:279
                x, y, x1, y1 = bbox
                res_frame_resized = cv2.resize(res_frame_np, (x1-x, y1-y))

                # 调试：打印 mask 信息
                if index == 0:
                    mask_for_blend = mask_list_cycle[idx]
                    logger.info(f"[Debug] mask shape: {mask_for_blend.shape}, dtype: {mask_for_blend.dtype}")
                    logger.info(f"[Debug] mask min: {mask_for_blend.min()}, max: {mask_for_blend.max()}")
                    logger.info(f"[Debug] mask_coords: {mask_coords_list_cycle[idx]}")
                    logger.info(f"[Debug] bbox: {bbox}")

                # 使用 get_image_blending 代替 get_image
                # get_image_blending 不需要 FaceParsing 模型
                combined_frame = get_image_blending(
                    ori_frame,
                    res_frame_resized,         # 使用 resize 后的 face
                    bbox,                      # face_box
                    mask_list_cycle[idx],      # mask_array
                    mask_coords_list_cycle[idx] # crop_box
                )
            except Exception as e:
                logger.error(f"Frame blending error: {e}")
                logger.error(f"Traceback: ", exc_info=True)
                combined_frame = ori_frame

            # 立即放入帧队列 ⚡
            res_frame_queue.put(combined_frame)
            if index % 10 == 0:  # 每10帧打印一次
                logger.info(f"✅ Put frame {index} into queue (qsize={res_frame_queue.qsize()})")
            index += 1

    logger.info('Inference thread stopped')


class MuseTalkRealtimeEngine:
    """
    MuseTalk 实时推理引擎 - 使用 threading.Thread

    完全参考 virtual-tutor/lip-sync/musereal.py
    """

    def __init__(
        self,
        avatar_id: str,
        avatar_path: str,
        musetalk_base: str,
        batch_size: int = 8
    ):
        self.avatar_id = avatar_id
        self.avatar_path = avatar_path
        self.musetalk_base = musetalk_base
        self.batch_size = batch_size

        # 队列（使用 Queue，threading 兼容）
        # 增大容量以避免阻塞（支持50个batch）
        self.audio_feat_queue = Queue(maxsize=50)
        self.res_frame_queue = Queue(maxsize=batch_size * 20)

        # 控制事件
        self.render_event = Event()

        # 推理线程
        self.inference_thread: Optional[Thread] = None

        # 模型（在 start() 时加载）
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

        logger.info(f"[{avatar_id}] Realtime Engine initialized")

    def start(self):
        """启动推理线程"""
        if self.inference_thread is not None:
            logger.warning(f"[{self.avatar_id}] Engine already started")
            return

        logger.info(f"[{self.avatar_id}] Loading models in main thread...")
        logger.info(f"[{self.avatar_id}] musetalk_base={self.musetalk_base}")
        logger.info(f"[{self.avatar_id}] Current sys.path has {len(sys.path)} entries")

        # 确保 MuseTalk 路径在 sys.path 中
        if self.musetalk_base not in sys.path:
            sys.path.insert(0, self.musetalk_base)
            logger.info(f"[{self.avatar_id}] Added {self.musetalk_base} to sys.path")
        else:
            logger.info(f"[{self.avatar_id}] {self.musetalk_base} already in sys.path")

        # 切换到 MuseTalk 目录（模型加载需要）
        original_cwd = os.getcwd()
        logger.info(f"[{self.avatar_id}] Changing directory from {original_cwd} to {self.musetalk_base}")
        os.chdir(self.musetalk_base)

        try:
            logger.info(f"[{self.avatar_id}] Attempting to import musetalk.utils.utils...")

            # 清除可能的模块缓存，并临时调整 sys.path
            import importlib
            
            # 保存原始 sys.path
            original_sys_path = sys.path.copy()
            
            # 清除所有 musetalk 相关的模块缓存
            mods_to_remove = [k for k in sys.modules.keys() if k == 'musetalk' or k.startswith('musetalk.')]
            for mod in mods_to_remove:
                del sys.modules[mod]
            
            # 把 MuseTalk 放到 sys.path 最前面
            sys.path = [self.musetalk_base] + [p for p in sys.path if p != self.musetalk_base]
            
            logger.info(f"[{self.avatar_id}] sys.path[0] = {sys.path[0]}")

            from musetalk.utils.utils import load_all_model
            from musetalk.whisper.audio2feature import Audio2Feature
            logger.info(f"[{self.avatar_id}] Import successful!")

            # 1. 加载 MuseTalk 模型（在主进程中）
            vae, unet, pe = load_all_model()

            # 2. 创建 audio processor
            audio_processor = Audio2Feature(
                whisper_model_type="tiny",
                model_path="tiny"
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

            # 3. 加载 Avatar 数据
            self._load_avatar_data()

            # 4. 启动推理线程（使用 Thread，不是 Process！）
            self.render_event.set()
            self.inference_thread = Thread(
                target=inference_loop,
                args=(
                    self.render_event,
                    self.batch_size,
                    self.input_latent_list_cycle,
                    self.coord_list_cycle,
                    self.frame_list_cycle,
                    self.mask_list_cycle,
                    self.mask_coords_list_cycle,
                    self.audio_feat_queue,
                    self.res_frame_queue,
                    self.vae, self.unet, self.pe, self.timesteps
                ),
                daemon=True
            )
            self.inference_thread.start()

            logger.info(f"[{self.avatar_id}] Inference thread started")

        finally:
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
        with open(coords_path, 'rb') as f:
            self.coord_list_cycle = pickle.load(f)

        # 加载原始图像
        full_imgs_path = os.path.join(self.avatar_path, "full_imgs")
        img_list = sorted(
            Path(full_imgs_path).glob("*.[jpJP][pnPN]*[gG]"),
            key=lambda x: int(x.stem)
        )
        self.frame_list_cycle = [cv2.imread(str(p)) for p in img_list]

        # 加载 mask
        mask_path = os.path.join(self.avatar_path, "mask")
        mask_coords_path = os.path.join(self.avatar_path, "mask_coords.pkl")

        with open(mask_coords_path, 'rb') as f:
            self.mask_coords_list_cycle = pickle.load(f)

        mask_list = sorted(
            Path(mask_path).glob("*.[jpJP][pnPN]*[gG]"),
            key=lambda x: int(x.stem)
        )
        self.mask_list_cycle = [cv2.imread(str(p)) for p in mask_list]

        logger.info(f"[{self.avatar_id}] Avatar data loaded: {len(self.coord_list_cycle)} frames")

    async def generate_frames(
        self,
        audio_data: str,
        fps: int = 25
    ) -> AsyncIterator[np.ndarray]:
        """
        生成帧流（异步）

        流程：
        1. 解码并转换音频格式（MP3 → WAV）
        2. 提取 Whisper 特征
        3. 放入队列
        4. 从帧队列实时读取并yield
        """
        import base64
        import tempfile
        import subprocess
        import soundfile as sf

        # 1. 解码音频
        audio_bytes = base64.b64decode(audio_data)

        # 检测音频格式并转换为 WAV（MuseTalk 需要 WAV 格式）
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
            # ⚠️ 重要：在开始新请求前清空队列，避免残留帧影响
            self._clear_queues()
            
            # 2. 提取 Whisper 特征
            logger.info(f"[{self.avatar_id}] Extracting audio features...")

            loop = asyncio.get_event_loop()

            def extract_features():
                whisper_feature = self.audio_processor.audio2feat(audio_path)
                # 与 try 保持一致：fps=50 → fps/2=25fps
                # 每帧视频对应 2 个音频 chunks (40ms)
                return self.audio_processor.feature2chunks(
                    feature_array=whisper_feature,
                    fps=fps / 2  # fps=50 → 25fps
                )

            whisper_chunks = await loop.run_in_executor(None, extract_features)

            logger.info(f"[{self.avatar_id}] Extracted {len(whisper_chunks)} chunks")

            # 3. 将 whisper_chunks 分批放入音频队列
            # 每个批次包含 batch_size 个 chunks
            batched_chunks = []
            for i in range(0, len(whisper_chunks), self.batch_size):
                batch = whisper_chunks[i:i + self.batch_size]
                if len(batch) == self.batch_size:  # 只处理完整的批次
                    batched_chunks.append(batch)

            logger.info(f"[{self.avatar_id}] Created {len(batched_chunks)} batches")

            # 4. 放入音频队列（异步，避免阻塞事件循环）
            for i, batch in enumerate(batched_chunks):
                await loop.run_in_executor(
                    None,
                    lambda b=batch: self.audio_feat_queue.put(b)
                )
                if i == 0:
                    logger.info(f"[{self.avatar_id}] ✅ First batch added to audio queue")

            logger.info(f"[{self.avatar_id}] All {len(batched_chunks)} batches added to audio queue")

            # 5. 从帧队列读取并 yield
            total_frames = len(batched_chunks) * self.batch_size
            frame_count = 0
            first_frame_time = None
            
            logger.info(f"[{self.avatar_id}] 🔄 Waiting for frames... (expected {total_frames} frames)")

            while frame_count < total_frames:
                try:
                    # 添加调试日志
                    if frame_count == 0:
                        logger.info(f"[{self.avatar_id}] 🔍 Queue status before first get: qsize={self.res_frame_queue.qsize()}")
                    
                    frame = await loop.run_in_executor(
                        None,
                        lambda: self.res_frame_queue.get(timeout=2)
                    )

                    if frame_count == 0:
                        first_frame_time = time.time()
                        logger.info(f"[{self.avatar_id}] ⚡ First frame generated!")

                    yield frame
                    frame_count += 1
                    
                    if frame_count % 10 == 0:
                        logger.info(f"[{self.avatar_id}] 📤 Yielded {frame_count}/{total_frames} frames")

                except Empty:
                    logger.warning(f"[{self.avatar_id}] ⏳ Queue timeout, retry... (frame_count={frame_count}, qsize={self.res_frame_queue.qsize()})")
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

    def _clear_queues(self):
        """清空音频和帧队列，避免残留数据影响新请求"""
        # 清空音频特征队列
        cleared_audio = 0
        while not self.audio_feat_queue.empty():
            try:
                self.audio_feat_queue.get_nowait()
                cleared_audio += 1
            except Empty:
                break
        
        # 清空帧队列
        cleared_frames = 0
        while not self.res_frame_queue.empty():
            try:
                self.res_frame_queue.get_nowait()
                cleared_frames += 1
            except Empty:
                break
        
        if cleared_audio > 0 or cleared_frames > 0:
            logger.info(f"[{self.avatar_id}] 🧹 Cleared queues: {cleared_audio} audio batches, {cleared_frames} frames")

    def stop(self):
        """停止推理线程"""
        self.render_event.clear()
        if self.inference_thread:
            self.inference_thread.join(timeout=5)
        logger.info(f"[{self.avatar_id}] Engine stopped")
