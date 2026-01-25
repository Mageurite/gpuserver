"""
简化的实时推理引擎 - 使用 subprocess 调用 mt 环境

直接使用旧的generate_video方式，但通过subprocess实时读取输出
"""

import asyncio
import base64
import logging
import os
import subprocess
import tempfile
import cv2
import numpy as np
from typing import Optional, AsyncIterator

logger = logging.getLogger(__name__)


class SimplifiedRealtimeEngine:
    """
    简化的实时引擎

    策略：使用 subprocess 调用 MuseTalk (mt 环境)，
    边生成边读取帧，而不是等待完整视频
    """

    def __init__(
        self,
        avatar_id: str,
        avatar_path: str,
        musetalk_base: str
    ):
        self.avatar_id = avatar_id
        self.avatar_path = avatar_path
        self.musetalk_base = musetalk_base

        logger.info(f"SimplifiedRealtimeEngine initialized for {avatar_id}")

    async def generate_frames(
        self,
        audio_data: str,
        fps: int = 25
    ) -> AsyncIterator[np.ndarray]:
        """
        生成帧流

        简化策略：
        1. 使用 mt 环境调用 MuseTalk 生成视频
        2. 实时读取视频文件（边生成边读取）
        3. 逐帧 yield

        Args:
            audio_data: base64 编码的音频数据
            fps: 视频帧率

        Yields:
            numpy.ndarray: 视频帧
        """
        import time

        try:
            # 1. 解码音频数据并保存
            audio_bytes = base64.b64decode(audio_data)

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as audio_file:
                audio_file.write(audio_bytes)
                audio_path = audio_file.name

            # 2. 准备输出路径
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as video_file:
                video_path = video_file.name

            try:
                # 3. 启动 MuseTalk 子进程 (mt 环境)
                python_bin = "/workspace/conda_envs/mt/bin/python"

                # 使用 realtime_inference 脚本
                cmd = [
                    python_bin, "-u", "-m", "scripts.realtime_inference",
                    "--inference_config", "./configs/inference/realtime.yaml",
                    "--result_dir", os.path.dirname(video_path),
                    "--fps", str(fps),
                    "--batch_size", "8"
                ]

                logger.info(f"[SimplifiedEngine] Starting MuseTalk subprocess...")

                # 启动子进程（非阻塞）
                process = subprocess.Popen(
                    cmd,
                    cwd=self.musetalk_base,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                # 4. 等待视频文件开始生成
                logger.info(f"[SimplifiedEngine] Waiting for video file...")
                wait_count = 0
                max_wait = 60  # 最多等60秒

                while wait_count < max_wait:
                    if os.path.exists(video_path) and os.path.getsize(video_path) > 1024:
                        logger.info(f"[SimplifiedEngine] Video file detected, starting streaming...")
                        break
                    await asyncio.sleep(0.5)
                    wait_count += 0.5

                if wait_count >= max_wait:
                    logger.error("[SimplifiedEngine] Timeout waiting for video file")
                    process.kill()
                    return

                # 5. 实时读取视频帧
                cap = cv2.VideoCapture(video_path)

                if not cap.isOpened():
                    logger.error(f"[SimplifiedEngine] Failed to open video: {video_path}")
                    process.kill()
                    return

                frame_count = 0
                first_frame_time = time.time()

                while True:
                    ret, frame = cap.read()

                    if not ret:
                        # 检查进程是否还在运行
                        if process.poll() is not None:
                            # 进程已结束，不会有更多帧了
                            break

                        # 进程还在运行，等待更多帧
                        await asyncio.sleep(0.04)  # 等待1帧时间
                        continue

                    if frame_count == 0:
                        delay = time.time() - first_frame_time
                        logger.info(f"[SimplifiedEngine] ⚡ First frame in {delay:.2f}s")

                    yield frame
                    frame_count += 1

                    # 控制帧率
                    await asyncio.sleep(1.0 / fps)

                cap.release()
                logger.info(f"[SimplifiedEngine] Streamed {frame_count} frames")

                # 等待进程结束
                process.wait(timeout=5)

            finally:
                # 清理临时文件
                try:
                    os.unlink(audio_path)
                    os.unlink(video_path)
                except:
                    pass

        except Exception as e:
            logger.error(f"[SimplifiedEngine] Failed: {e}", exc_info=True)
