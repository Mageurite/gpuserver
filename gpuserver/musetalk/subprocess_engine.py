"""
Subprocess Realtime Engine - 通过 subprocess 启动 mt 环境的推理服务

参考 virtual-tutor 的 live_server.py 启动方式
"""

import logging
import subprocess
import time
import os
import signal
import requests
import base64
from typing import Optional, AsyncIterator
import asyncio
import aiohttp

logger = logging.getLogger(__name__)


class SubprocessRealtimeEngine:
    """
    通过 subprocess 启动独立推理服务

    架构：
    - 主进程（rag环境）：avatar_manager.py
    - 子进程（mt环境）：realtime_inference_service.py
    - 通信方式：HTTP API
    """

    def __init__(
        self,
        avatar_id: str,
        avatar_path: str,
        port: int = 9100,
        batch_size: int = 8,
        mt_conda_env: str = "/workspace/conda_envs/mt",
        service_script: str = "/workspace/gpuserver/musetalk/realtime_inference_service.py"
    ):
        self.avatar_id = avatar_id
        self.avatar_path = avatar_path
        self.port = port
        self.batch_size = batch_size
        self.mt_conda_env = mt_conda_env
        self.service_script = service_script

        self.process: Optional[subprocess.Popen] = None
        self.service_url = f"http://127.0.0.1:{port}"

        logger.info(f"[{avatar_id}] SubprocessEngine initialized on port {port}")

    def start(self):
        """启动推理服务进程"""
        if self.process is not None:
            logger.warning(f"[{self.avatar_id}] Process already started")
            return

        # 构建启动命令
        python_bin = os.path.join(self.mt_conda_env, "bin", "python")

        command = [
            python_bin,
            self.service_script,
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "--avatar-id", self.avatar_id,
            "--avatar-path", self.avatar_path,
            "--batch-size", str(self.batch_size)
        ]

        logger.info(f"[{self.avatar_id}] Starting inference service: {' '.join(command)}")

        try:
            # 启动子进程
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                preexec_fn=os.setsid  # 创建新的进程组，便于管理
            )

            logger.info(f"[{self.avatar_id}] Process started with PID: {self.process.pid}")

            # 等待服务启动
            self._wait_for_service()

        except Exception as e:
            logger.error(f"[{self.avatar_id}] Failed to start process: {e}")
            raise

    def _wait_for_service(self, timeout: int = 90):
        """等待服务启动（模型加载需要较长时间）"""
        logger.info(f"[{self.avatar_id}] Waiting for service to start (may take up to {timeout}s for model loading)...")

        start_time = time.time()
        health_url = f"{self.service_url}/health"

        while time.time() - start_time < timeout:
            try:
                response = requests.get(health_url, timeout=1)
                if response.status_code == 200:
                    logger.info(f"[{self.avatar_id}] ✅ Service started successfully")
                    return
            except requests.exceptions.RequestException:
                pass

            time.sleep(0.5)

        raise TimeoutError(f"[{self.avatar_id}] Service failed to start within {timeout}s")

    async def generate_frames(
        self,
        audio_data: str,
        fps: int = 25
    ) -> AsyncIterator[bytes]:
        """
        生成视频帧流

        Args:
            audio_data: base64编码的音频数据
            fps: 帧率

        Yields:
            bytes: JPEG编码的视频帧
        """
        if not self.is_alive():
            raise RuntimeError(f"[{self.avatar_id}] Service is not running")

        # 准备请求
        generate_url = f"{self.service_url}/generate"
        payload = {
            "audio_data": audio_data,
            "fps": fps
        }

        logger.info(f"[{self.avatar_id}] Sending generation request...")

        # 使用 aiohttp 流式接收
        timeout = aiohttp.ClientTimeout(total=300)  # 5分钟超时
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(generate_url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"[{self.avatar_id}] Generation failed: {response.status} - {error_text}"
                    )

                # 读取 multipart 流
                boundary = b'frame'
                buffer = b''

                frame_count = 0
                first_frame_time = None

                async for chunk in response.content.iter_any():
                    buffer += chunk

                    # 解析 multipart 帧
                    while True:
                        # 查找边界
                        start = buffer.find(b'--' + boundary)
                        if start == -1:
                            break

                        # 查找内容类型
                        content_start = buffer.find(b'\r\n\r\n', start)
                        if content_start == -1:
                            break

                        content_start += 4

                        # 查找下一个边界
                        next_boundary = buffer.find(b'--' + boundary, content_start)
                        if next_boundary == -1:
                            break

                        # 提取帧数据
                        frame_data = buffer[content_start:next_boundary - 2]  # 去掉结尾的\r\n

                        if frame_data:
                            if frame_count == 0:
                                first_frame_time = time.time()
                                logger.info(f"[{self.avatar_id}] ⚡ First frame received!")

                            yield frame_data
                            frame_count += 1

                        # 更新缓冲区
                        buffer = buffer[next_boundary:]

                if first_frame_time:
                    total_time = time.time() - first_frame_time
                    logger.info(
                        f"[{self.avatar_id}] Received {frame_count} frames "
                        f"in {total_time:.2f}s (avg {frame_count/total_time:.2f} fps)"
                    )

    def is_alive(self) -> bool:
        """检查服务是否运行"""
        if self.process is None:
            return False

        # 检查进程状态
        if self.process.poll() is not None:
            return False

        # 检查服务健康
        try:
            response = requests.get(f"{self.service_url}/health", timeout=1)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def stop(self):
        """停止推理服务进程"""
        if self.process is None:
            return

        logger.info(f"[{self.avatar_id}] Stopping inference service (PID: {self.process.pid})...")

        try:
            # 发送 SIGTERM 给进程组
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)

            # 等待进程退出
            try:
                self.process.wait(timeout=5)
                logger.info(f"[{self.avatar_id}] Process stopped gracefully")
            except subprocess.TimeoutExpired:
                # 强制杀死
                logger.warning(f"[{self.avatar_id}] Force killing process")
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                self.process.wait()

        except Exception as e:
            logger.error(f"[{self.avatar_id}] Error stopping process: {e}")

        finally:
            self.process = None

    def __del__(self):
        """析构函数 - 确保进程被清理"""
        self.stop()
