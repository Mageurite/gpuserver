import asyncio
import base64
import logging
from typing import Optional, Dict
from threading import Lock

logger = logging.getLogger(__name__)


class AIEngine:
    """
    AI 推理引擎

    这是一个 Mock 实现，用于演示接口。
    在生产环境中，应该替换为真实的 AI 模型调用（LLM/ASR/TTS/MuseTalk）
    
    注意：每个 AIEngine 实例对应一个 tutor_id，实现模型隔离
    """

    def __init__(self, tutor_id: int):
        """
        初始化 AI 引擎

        Args:
            tutor_id: 导师 ID，用于标识不同的模型实例
        """
        self.tutor_id = tutor_id
        logger.info(f"AI Engine initialized for tutor_id={tutor_id} (Mock mode)")

    async def process_text(
        self,
        text: str,
        tutor_id: int,
        kb_id: Optional[str] = None
    ) -> str:
        """
        处理文本输入，生成 AI 响应

        Args:
            text: 用户输入的文本
            tutor_id: 导师 ID（用于验证，应该与实例的 tutor_id 一致）
            kb_id: 知识库 ID（可选，用于 RAG）

        Returns:
            str: AI 生成的响应文本
        """
        # 验证 tutor_id 是否匹配
        if tutor_id != self.tutor_id:
            logger.warning(f"tutor_id mismatch: instance={self.tutor_id}, request={tutor_id}")
        
        logger.info(f"Processing text: tutor_id={tutor_id}, kb_id={kb_id}, text={text[:50]}...")

        # 模拟处理延迟
        await asyncio.sleep(0.5)

        # Mock LLM 响应（包含 tutor_id 标识，表示使用独立的模型实例）
        if kb_id:
            response = (
                f"[Mock Response - Tutor {tutor_id} Model Instance] "
                f"使用知识库 {kb_id} 的回答："
                f"您好！我是虚拟导师 #{tutor_id}。"
                f"关于您的问题「{text}」，根据知识库的内容，我的回答是：这是一个基于知识库检索的模拟回答。"
            )
        else:
            response = (
                f"[Mock Response - Tutor {tutor_id} Model Instance] "
                f"您好！我是虚拟导师 #{tutor_id}。"
                f"您刚才说：「{text}」。这是一个模拟的 AI 回复。"
                f"在真实环境中，这里会调用 LLM 模型生成智能回复。"
            )

        logger.info(f"Generated response: {response[:100]}...")
        return response

    async def process_audio(self, audio_data: str) -> str:
        """
        处理音频输入（ASR: 语音转文本）

        Args:
            audio_data: base64 编码的音频数据

        Returns:
            str: 转录的文本
        """
        logger.info(f"Processing audio (tutor_id={self.tutor_id}): data_length={len(audio_data)}")

        # 模拟 ASR 处理延迟
        await asyncio.sleep(0.3)

        # Mock ASR 转录结果
        transcription = f"[Mock ASR - Tutor {self.tutor_id}] 这是一段模拟的语音转文本结果"

        logger.info(f"Transcribed: {transcription}")
        return transcription

    async def synthesize_speech(self, text: str) -> str:
        """
        文本转语音（TTS）

        Args:
            text: 要合成的文本

        Returns:
            str: base64 编码的音频数据
        """
        logger.info(f"Synthesizing speech (tutor_id={self.tutor_id}): text={text[:50]}...")

        # 模拟 TTS 处理延迟
        await asyncio.sleep(0.4)

        # Mock 音频数据（实际应该是 WAV/MP3 的 base64）
        mock_audio = b"MOCK_AUDIO_DATA_TUTOR_" + str(self.tutor_id).encode('utf-8') + b"_" + text.encode('utf-8')[:20]
        audio_base64 = base64.b64encode(mock_audio).decode('utf-8')

        logger.info(f"Synthesized audio: length={len(audio_base64)}")
        return audio_base64


# 按 tutor_id 隔离的 AI 引擎实例缓存
_tutor_engines: Dict[int, AIEngine] = {}
_engines_lock = Lock()


def get_ai_engine(tutor_id: int) -> AIEngine:
    """
    获取指定 tutor_id 的 AI 引擎实例
    
    实现按 tutor_id 隔离模型：
    - 每个 tutor_id 对应一个独立的 AIEngine 实例
    - 不同 tutor 使用不同的模型实例
    - 模型实例会被缓存，避免重复创建
    
    Args:
        tutor_id: 导师 ID
        
    Returns:
        AIEngine: 对应 tutor_id 的 AI 引擎实例
    """
    global _tutor_engines
    
    # 如果已存在，直接返回
    if tutor_id in _tutor_engines:
        return _tutor_engines[tutor_id]
    
    # 线程安全地创建新实例
    with _engines_lock:
        # 双重检查，避免并发创建
        if tutor_id not in _tutor_engines:
            _tutor_engines[tutor_id] = AIEngine(tutor_id=tutor_id)
            logger.info(f"Created new AI Engine instance for tutor_id={tutor_id}")
        
        return _tutor_engines[tutor_id]


def remove_ai_engine(tutor_id: int) -> bool:
    """
    移除指定 tutor_id 的 AI 引擎实例（用于清理）
    
    Args:
        tutor_id: 导师 ID
        
    Returns:
        bool: 是否成功移除
    """
    global _tutor_engines
    
    with _engines_lock:
        if tutor_id in _tutor_engines:
            del _tutor_engines[tutor_id]
            logger.info(f"Removed AI Engine instance for tutor_id={tutor_id}")
            return True
        return False


def get_all_tutor_ids() -> list:
    """
    获取所有已创建 AI 引擎的 tutor_id 列表
    
    Returns:
        list: tutor_id 列表
    """
    with _engines_lock:
        return list(_tutor_engines.keys())


# TODO: 在真实环境中，需要实现以下模块：
#
# class RealAIEngine(AIEngine):
#     def __init__(self):
#         # 初始化 LLM 模型
#         self.llm = load_llm_model()
#
#         # 初始化 ASR 模型
#         self.asr = load_asr_model()
#
#         # 初始化 TTS 模型
#         self.tts = load_tts_model()
#
#         # 初始化 RAG 检索器
#         self.rag = load_rag_retriever()
#
#     async def process_text(self, text, tutor_id, kb_id):
#         # 1. RAG 检索（如果有 kb_id）
#         context = await self.rag.retrieve(text, kb_id) if kb_id else None
#
#         # 2. LLM 生成
#         response = await self.llm.generate(text, context)
#
#         return response
#
#     async def process_audio(self, audio_data):
#         # ASR 转录
#         audio_bytes = base64.b64decode(audio_data)
#         transcription = await self.asr.transcribe(audio_bytes)
#         return transcription
#
#     async def synthesize_speech(self, text):
#         # TTS 合成
#         audio_bytes = await self.tts.synthesize(text)
#         return base64.b64encode(audio_bytes).decode('utf-8')
