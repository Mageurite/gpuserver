import asyncio
import base64
import logging
from typing import Optional, Dict
from threading import Lock

# Initialize logger first
logger = logging.getLogger(__name__)

# Import LLM engine from llm module
from llm import get_llm_engine
# Import ASR engine from asr module
from asr import get_asr_engine
# Import TTS engine from tts module
from tts import get_tts_engine
# Import RAG engine from rag module
from rag import get_rag_engine
# Import Video engine from musetalk module
from musetalk import get_video_engine

from config import get_settings

settings = get_settings()


class AIEngine:
    """
    AI 推理引擎
    
    支持真实的 LLM 调用（通过 Ollama）或 Mock 模式。
    每个 AIEngine 实例对应一个 tutor_id，实现模型隔离。
    
    注意：每个 tutor_id 可以使用不同的 LLM 模型（通过环境变量配置）
    """

    def __init__(self, tutor_id: int):
        """
        初始化 AI 引擎

        Args:
            tutor_id: 导师 ID，用于标识不同的模型实例
        """
        self.tutor_id = tutor_id

        # 初始化 LLM 引擎（从 llm 模块获取）
        self.llm_engine = get_llm_engine(tutor_id)

        # 初始化 ASR 引擎（从 asr 模块获取）
        self.asr_engine = get_asr_engine(
            model_name=settings.asr_model,
            enable_real=settings.enable_asr,
            device=settings.asr_device
        )

        # 初始化 TTS 引擎（从 tts 模块获取）
        self.tts_engine = get_tts_engine(
            voice=settings.tts_voice,
            enable_real=settings.enable_tts
        )

        # 初始化 RAG 引擎（从 rag 模块获取）
        self.rag_engine = get_rag_engine(
            enable_real=settings.enable_rag,
            rag_url=settings.rag_url,
            top_k=settings.rag_top_k
        )

        # 初始化 Video 引擎（从 video 模块获取）
        self.video_engine = get_video_engine(
            enable_real=settings.enable_avatar,
            musetalk_base=settings.musetalk_base,
            avatars_dir=settings.avatars_dir,
            conda_env=settings.musetalk_conda_env
        )

        logger.info(f"AI Engine initialized for tutor_id={tutor_id}")

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
            kb_id: 知识库 ID（可选，用于 RAG，当前版本暂未实现 RAG 检索）

        Returns:
            str: AI 生成的响应文本
        """
        # 验证 tutor_id 是否匹配
        if tutor_id != self.tutor_id:
            logger.warning(f"tutor_id mismatch: instance={self.tutor_id}, request={tutor_id}")
        
        logger.info(f"Processing text: tutor_id={tutor_id}, kb_id={kb_id}, text={text[:50]}...")

        # RAG 检索：如果 kb_id 存在，先进行知识库检索
        context = None
        if kb_id:
            logger.info(f"Performing RAG retrieval for kb_id={kb_id}")
            try:
                # 检索相关文档
                retrieved_docs = await self.rag_engine.retrieve(
                    query=text,
                    kb_id=kb_id,
                    user_id=tutor_id  # 使用 tutor_id 作为 user_id
                )

                # 格式化为 LLM 上下文
                context = self.rag_engine.format_context(retrieved_docs)
                logger.info(f"RAG retrieved {len(retrieved_docs)} documents")
            except Exception as e:
                logger.error(f"RAG retrieval failed: {e}, using direct LLM")
                context = None

        # 调用 LLM 引擎生成响应
        response = await self.llm_engine.generate(text=text, context=context)
        
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

        # 调用 ASR 引擎进行转录
        transcription = await self.asr_engine.transcribe(
            audio_data=audio_data,
            language=settings.asr_language
        )

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

        # 调用 TTS 引擎进行语音合成
        audio_data = await self.tts_engine.synthesize(
            text=text,
            language=settings.asr_language  # 使用与 ASR 相同的语言设置
        )

        logger.info(f"Synthesized audio: length={len(audio_data)}")
        return audio_data

    async def generate_video(
        self,
        audio_data: str,
        avatar_id: str,
        fps: int = 25
    ) -> Optional[str]:
        """
        生成口型同步视频（Avatar + Audio）

        Args:
            audio_data: base64 编码的音频数据
            avatar_id: Avatar ID
            fps: 视频帧率

        Returns:
            str: base64 编码的视频数据，失败返回 None
        """
        logger.info(f"Generating video (tutor_id={self.tutor_id}): avatar_id={avatar_id}")

        # 调用 Video 引擎生成视频
        video_data = await self.video_engine.generate_video(
            audio_data=audio_data,
            avatar_id=avatar_id,
            fps=fps
        )

        if video_data:
            logger.info(f"Video generated: length={len(video_data)}")
        else:
            logger.error("Video generation failed")

        return video_data

    async def get_idle_video(
        self,
        avatar_id: str,
        duration: int = 5,
        fps: int = 25
    ) -> Optional[str]:
        """
        获取 Avatar 的待机视频（循环播放的静态视频）

        Args:
            avatar_id: Avatar ID
            duration: 视频时长（秒）
            fps: 视频帧率

        Returns:
            str: base64 编码的待机视频数据，失败返回 None
        """
        logger.info(f"Getting idle video (tutor_id={self.tutor_id}): avatar_id={avatar_id}")

        # 调用 Video 引擎获取待机视频
        video_data = await self.video_engine.get_idle_video(
            avatar_id=avatar_id,
            duration=duration,
            fps=fps
        )

        if video_data:
            logger.info(f"Idle video retrieved: length={len(video_data)}")
        else:
            logger.error("Failed to get idle video")

        return video_data


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
