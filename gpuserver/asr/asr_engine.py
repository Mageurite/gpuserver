"""
ASR Engine Implementation

Supports:
1. Real Whisper model (using openai-whisper or faster-whisper)
2. Mock mode for testing
"""

import asyncio
import base64
import io
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class ASREngine:
    """
    ASR 引擎 - 将音频转换为文本

    支持:
    - Whisper 模型（openai-whisper）
    - Mock 模式（用于测试）
    """

    def __init__(
        self,
        model_name: str = "base",
        enable_real: bool = True,
        device: str = "cuda"
    ):
        """
        初始化 ASR 引擎

        Args:
            model_name: Whisper 模型名称 (tiny, base, small, medium, large)
            enable_real: 是否启用真实 ASR（False 则使用 Mock）
            device: 设备 ("cuda" 或 "cpu")
        """
        self.model_name = model_name
        self.enable_real = enable_real
        self.device = device
        self.model = None

        if self.enable_real:
            try:
                self._load_model()
                logger.info(f"ASR Engine initialized with model={model_name}, device={device}")
            except Exception as e:
                logger.error(f"Failed to load ASR model: {e}")
                logger.warning("Falling back to Mock ASR mode")
                self.enable_real = False
        else:
            logger.info("ASR Engine initialized in Mock mode")

    def _load_model(self):
        """加载 Whisper 模型"""
        try:
            import whisper
            self.model = whisper.load_model(
                self.model_name,
                device=self.device
            )
            logger.info(f"Whisper model '{self.model_name}' loaded successfully")
        except ImportError:
            logger.error("whisper package not installed. Install with: pip install openai-whisper")
            raise
        except Exception as e:
            logger.error(f"Error loading Whisper model: {e}")
            raise

    async def transcribe(self, audio_data: str, language: str = "zh") -> str:
        """
        将音频转换为文本

        Args:
            audio_data: base64 编码的音频数据（支持多种格式：WAV, MP3, OGG, WebM 等）
            language: 语言代码（zh: 中文, en: 英文）

        Returns:
            str: 转录的文本
        """
        if not self.enable_real or self.model is None:
            # Mock 模式
            return await self._mock_transcribe(audio_data)

        try:
            # 在线程池中运行同步的 Whisper 调用
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                audio_data,
                language
            )
            return result
        except Exception as e:
            logger.error(f"ASR transcription failed: {e}")
            # 降级到 Mock 模式
            return await self._mock_transcribe(audio_data)

    def _transcribe_sync(self, audio_data: str, language: str) -> str:
        """
        同步转录音频（在线程池中运行）

        Args:
            audio_data: base64 编码的音频数据
            language: 语言代码

        Returns:
            str: 转录的文本
        """
        import tempfile
        import numpy as np
        import soundfile as sf

        # 1. 解码 base64
        audio_bytes = base64.b64decode(audio_data)

        # 2. 保存到临时文件（Whisper 需要文件路径）
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            tmp_file.write(audio_bytes)

        try:
            # 3. 调用 Whisper 进行转录
            result = self.model.transcribe(
                tmp_path,
                language=language,
                fp16=self.device == "cuda"  # 使用 FP16 加速（仅 CUDA）
            )

            # 4. 提取文本
            text = result["text"].strip()
            logger.info(f"ASR transcribed: {text[:100]}...")

            return text

        finally:
            # 5. 清理临时文件
            try:
                os.unlink(tmp_path)
            except:
                pass

    async def _mock_transcribe(self, audio_data: str) -> str:
        """
        Mock 转录（用于测试）

        Args:
            audio_data: base64 编码的音频数据

        Returns:
            str: Mock 转录结果
        """
        # 模拟处理延迟
        await asyncio.sleep(0.3)

        # Mock 结果
        return "[Mock ASR] 这是一段模拟的语音转文本结果"


# 全局 ASR 引擎实例
_asr_engine: Optional[ASREngine] = None


def get_asr_engine(
    model_name: str = "base",
    enable_real: bool = True,
    device: str = "cuda"
) -> ASREngine:
    """
    获取 ASR 引擎实例（单例模式）

    Args:
        model_name: Whisper 模型名称
        enable_real: 是否启用真实 ASR
        device: 设备

    Returns:
        ASREngine: ASR 引擎实例
    """
    global _asr_engine

    if _asr_engine is None:
        _asr_engine = ASREngine(
            model_name=model_name,
            enable_real=enable_real,
            device=device
        )

    return _asr_engine
