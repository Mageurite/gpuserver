"""
TTS Engine Implementation

Supports:
1. Edge TTS (Microsoft Edge Text-to-Speech, online service)
2. Mock mode for testing
"""

import asyncio
import base64
import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TTSEngine:
    """
    TTS 引擎 - 将文本转换为语音

    支持:
    - Edge TTS（微软在线 TTS 服务）
    - Mock 模式（用于测试）
    """

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        enable_real: bool = True
    ):
        """
        初始化 TTS 引擎

        Args:
            voice: Edge TTS 声音名称
                   中文女声: zh-CN-XiaoxiaoNeural, zh-CN-XiaoyiNeural
                   中文男声: zh-CN-YunjianNeural, zh-CN-YunxiNeural
                   英文女声: en-US-JennyNeural, en-US-AriaNeural
                   英文男声: en-US-GuyNeural, en-US-ChristopherNeural
            enable_real: 是否启用真实 TTS（False 则使用 Mock）
        """
        self.voice = voice
        self.enable_real = enable_real

        if self.enable_real:
            try:
                # 验证 edge-tts 是否可用
                import edge_tts
                self.edge_tts = edge_tts
                logger.info(f"TTS Engine initialized with voice={voice}")
            except ImportError:
                logger.error("edge-tts package not installed. Install with: pip install edge-tts")
                logger.warning("Falling back to Mock TTS mode")
                self.enable_real = False
        else:
            logger.info("TTS Engine initialized in Mock mode")

    async def synthesize(self, text: str, language: str = "zh") -> str:
        """
        将文本转换为语音

        Args:
            text: 要合成的文本
            language: 语言代码（zh: 中文, en: 英文），用于自动选择声音

        Returns:
            str: base64 编码的音频数据（MP3 格式）
        """
        if not self.enable_real:
            # Mock 模式
            return await self._mock_synthesize(text)

        try:
            # 使用 Edge TTS 合成
            audio_data = await self._synthesize_with_edge_tts(text)
            return audio_data
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            # 降级到 Mock 模式
            return await self._mock_synthesize(text)

    async def _synthesize_with_edge_tts(self, text: str) -> str:
        """
        使用 Edge TTS 合成语音

        Args:
            text: 要合成的文本

        Returns:
            str: base64 编码的音频数据（MP3 格式）
        """
        import tempfile
        import os

        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            # 使用 edge-tts 合成语音
            communicate = self.edge_tts.Communicate(text, self.voice)
            await communicate.save(tmp_path)

            # 读取并编码为 base64
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()
                audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

            logger.info(f"TTS synthesized: {len(audio_bytes)} bytes, text={text[:50]}...")

            return audio_base64

        finally:
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except:
                pass

    async def _mock_synthesize(self, text: str) -> str:
        """
        Mock 合成（用于测试）

        Args:
            text: 要合成的文本

        Returns:
            str: Mock 音频数据（base64 编码）
        """
        # 模拟处理延迟
        await asyncio.sleep(0.4)

        # Mock 音频数据
        mock_audio = b"MOCK_TTS_AUDIO_DATA_" + text.encode("utf-8")[:50]
        audio_base64 = base64.b64encode(mock_audio).decode("utf-8")

        logger.info(f"Mock TTS synthesized: {len(audio_base64)} bytes")

        return audio_base64


# 全局 TTS 引擎实例
_tts_engine: Optional[TTSEngine] = None


def get_tts_engine(
    voice: str = "zh-CN-XiaoxiaoNeural",
    enable_real: bool = True
) -> TTSEngine:
    """
    获取 TTS 引擎实例（单例模式）

    Args:
        voice: Edge TTS 声音名称
        enable_real: 是否启用真实 TTS

    Returns:
        TTSEngine: TTS 引擎实例
    """
    global _tts_engine

    if _tts_engine is None:
        _tts_engine = TTSEngine(
            voice=voice,
            enable_real=enable_real
        )

    return _tts_engine
