import asyncio
import base64
import logging
from typing import Optional, Dict, AsyncIterator
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
from musetalk import get_video_engine, get_streaming_engine, warmup_streaming_engine

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

        # 添加 avatar_manager 别名（用于 websocket_server 中的预热调用）
        self.avatar_manager = self.video_engine

        logger.info(f"AI Engine initialized for tutor_id={tutor_id}")

    async def process_text(
        self,
        text: str,
        tutor_id: int,
        kb_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> str:
        """
        处理文本输入，生成 AI 响应

        Args:
            text: 用户输入的文本
            tutor_id: 导师 ID（用于验证，应该与实例的 tutor_id 一致）
            kb_id: 知识库 ID（可选，用于 RAG，当前版本暂未实现 RAG 检索）
            session_id: 会话 ID（可选，用于区分不同的聊天历史）

        Returns:
            str: AI 生成的响应文本
        """
        # 验证 tutor_id 是否匹配
        if tutor_id != self.tutor_id:
            logger.warning(f"tutor_id mismatch: instance={self.tutor_id}, request={tutor_id}")

        logger.info(f"Processing text: tutor_id={tutor_id}, kb_id={kb_id}, session_id={session_id}, text={text[:50]}...")

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

    async def stream_text_response(
        self,
        text: str,
        tutor_id: int = None,
        kb_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        流式处理文本响应（逐 token 输出）

        Args:
            text: 用户输入的文本
            tutor_id: 导师 ID（用于验证，应该与实例的 tutor_id 一致）
            kb_id: 知识库 ID（可选，用于 RAG）
            session_id: 会话 ID（可选，用于区分不同的聊天历史）

        Yields:
            str: LLM 生成的 token 流
        """
        # 验证 tutor_id 是否匹配
        if tutor_id and tutor_id != self.tutor_id:
            logger.warning(f"tutor_id mismatch: instance={self.tutor_id}, request={tutor_id}")

        logger.info(f"Streaming text response: tutor_id={tutor_id}, kb_id={kb_id}, session_id={session_id}, text={text[:50]}...")

        # RAG 检索：如果 kb_id 存在，先进行知识库检索
        context = None
        if kb_id:
            logger.info(f"Performing RAG retrieval for kb_id={kb_id}")
            try:
                # 检索相关文档
                retrieved_docs = await self.rag_engine.retrieve(
                    query=text,
                    kb_id=kb_id,
                    user_id=tutor_id or self.tutor_id  # 使用 tutor_id 作为 user_id
                )

                # 格式化为 LLM 上下文
                context = self.rag_engine.format_context(retrieved_docs)
                logger.info(f"RAG retrieved {len(retrieved_docs)} documents")
            except Exception as e:
                logger.error(f"RAG retrieval failed: {e}, using direct LLM")
                context = None

        # 流式生成 LLM 响应
        async for token in self.llm_engine.stream_generate(text=text, context=context):
            yield token

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

    async def stream_video_webrtc(
        self,
        text: str,
        avatar_id: str,
        session_id: str,
        fps: int = 25
    ):
        """
        通过 WebRTC 实时流式传输视频

        处理流程:
        1. LLM 生成文本响应
        2. TTS 生成音频
        3. MuseTalk 逐帧生成视频
        4. 每生成一帧就通过 WebRTC 推送

        Args:
            text: 用户输入文本
            avatar_id: Avatar ID
            session_id: 会话 ID（用于 WebRTC 连接）
            fps: 视频帧率

        Returns:
            tuple: (response_text, audio_data) 文本响应和音频数据
        """
        logger.info(f"Starting WebRTC video streaming (tutor_id={self.tutor_id}): avatar_id={avatar_id}")

        # 1. LLM 生成文本响应
        response_text = await self.process_text(
            text=text,
            tutor_id=self.tutor_id
        )

        # 2. TTS 生成音频
        audio_data = await self.synthesize_speech(response_text)

        # 3. 获取 WebRTC streamer
        from webrtc_streamer import get_webrtc_streamer
        streamer = get_webrtc_streamer()

        # 4. 延迟音频推送，等视频开始生成后再同步推送
        audio_task = None
        audio_started = False

        # 5. 实时生成并推流视频帧
        frame_count = 0
        async for frame in self.video_engine.generate_frames_stream(
            audio_data=audio_data,
            avatar_id=avatar_id,
            fps=fps
        ):
            # 在推送第一帧视频时，同时启动音频推送（实现音视频同步）
            if not audio_started:
                audio_task = asyncio.create_task(streamer.stream_audio(session_id, audio_data))
                audio_started = True
                logger.info(f"✅ Started audio streaming synchronized with video for session {session_id}")

            # 推送帧到 WebRTC
            await streamer.stream_frame(session_id, frame)
            frame_count += 1

            if frame_count % 25 == 0:  # 每秒日志一次
                logger.info(f"Streamed {frame_count} frames to session {session_id}")

        logger.info(f"WebRTC streaming completed: {frame_count} frames")

        # 等待音频推送完成
        if audio_task:
            await audio_task
            logger.info(f"Audio streaming completed for session {session_id}")

        return response_text, audio_data

    async def stream_video_realtime(
        self,
        text: str,
        avatar_id: str,
        session_id: str,
        fps: int = 25
    ):
        """
        真正的实时流式处理 - 使用 StreamingLipSyncEngine
        
        实现边TTS边生成视频边推流，首帧延迟 < 2秒
        
        处理流程（并行）:
        1. 文本 → TTS Worker → 音频chunks (20ms)
        2. 音频chunks → ASR → Whisper特征
        3. Whisper特征 → MuseTalk推理 → 视频帧
        4. 视频帧 + 音频帧 → WebRTC推流（同步）
        
        Args:
            text: 用户输入文本（已经是LLM响应）
            avatar_id: Avatar ID
            session_id: 会话 ID（用于 WebRTC 连接）
            fps: 视频帧率
            
        Returns:
            int: 推送的帧数
        """
        import os
        
        logger.info(f"[Realtime Streaming] Starting for avatar: {avatar_id}")
        
        # 1. 获取或创建流式引擎
        avatar_path = os.path.join(settings.avatars_dir, avatar_id)
        if not os.path.exists(avatar_path):
            logger.error(f"Avatar not found: {avatar_path}")
            return 0
            
        engine = get_streaming_engine(
            avatar_id=avatar_id,
            avatar_path=avatar_path,
            batch_size=8,
            fps=50,  # 音频帧率 50fps = 20ms/chunk
            voice=settings.tts_voice,
            tts_rate=settings.tts_rate,
            tts_pitch=settings.tts_pitch
        )
        
        # 2. 获取 WebRTC streamer
        from webrtc_streamer import get_webrtc_streamer
        streamer = get_webrtc_streamer()
        
        # 3. 实时处理文本，生成同步的音视频帧
        frame_count = 0
        audio_started = False
        
        async for video_frame, audio_samples in engine.process_text(text):
            # 推送视频帧
            await streamer.stream_frame(session_id, video_frame)
            
            # 推送音频（将float32转为int16）
            audio_int16 = (audio_samples * 32767).astype('int16')
            # TODO: 需要在 WebRTCStreamer 中添加 stream_audio_samples 方法
            # await streamer.stream_audio_samples(session_id, audio_int16)
            
            frame_count += 1
            
            if frame_count == 1:
                logger.info(f"⚡ First frame pushed to WebRTC for session {session_id}")
                
            if frame_count % 25 == 0:
                logger.info(f"Streamed {frame_count} frames to session {session_id}")
                
        logger.info(f"[Realtime Streaming] Completed: {frame_count} frames")
        return frame_count

    async def stream_text_and_video_realtime(
        self,
        text: str,
        avatar_id: str,
        session_id: str,
        tutor_id: int = None,
        kb_id: Optional[str] = None,
        fps: int = 25
    ):
        """
        完整的实时流式处理 - LLM + TTS + Lip-Sync
        
        处理流程:
        1. LLM 流式生成文本
        2. 每收集完整句子就发送到 TTS
        3. TTS 边生成边推送到 MuseTalk
        4. 视频帧实时推送到 WebRTC
        
        Args:
            text: 用户输入文本（问题）
            avatar_id: Avatar ID
            session_id: 会话 ID
            tutor_id: 导师 ID
            kb_id: 知识库 ID
            fps: 视频帧率
            
        Returns:
            str: 完整的 LLM 响应文本
        """
        import os
        import re
        
        logger.info(f"[Full Realtime Streaming] Starting for avatar: {avatar_id}")
        
        # 1. 获取或创建流式引擎
        avatar_path = os.path.join(settings.avatars_dir, avatar_id)
        if not os.path.exists(avatar_path):
            logger.error(f"Avatar not found: {avatar_path}")
            return ""
            
        engine = get_streaming_engine(
            avatar_id=avatar_id,
            avatar_path=avatar_path,
            batch_size=8,
            fps=50,
            voice=settings.tts_voice,
            tts_rate=settings.tts_rate,
            tts_pitch=settings.tts_pitch
        )
        
        # 2. 流式生成 LLM 响应
        full_response = ""
        sentence_buffer = ""
        sentence_endings = re.compile(r'[。！？.!?]')
        
        async for token in self.stream_text_response(
            text=text,
            tutor_id=tutor_id or self.tutor_id,
            kb_id=kb_id
        ):
            full_response += token
            sentence_buffer += token
            
            # 检查是否有完整句子
            if sentence_endings.search(sentence_buffer):
                # 找到句子结束符，发送到TTS
                sentences = sentence_endings.split(sentence_buffer)
                for i, sentence in enumerate(sentences[:-1]):
                    if sentence.strip():
                        engine.tts.put_text(sentence.strip() + sentences[i+1] if i+1 < len(sentences) else sentence.strip())
                        logger.info(f"[Realtime] Sent sentence to TTS: {sentence[:30]}...")
                sentence_buffer = sentences[-1] if sentences[-1] else ""
                
        # 发送剩余的文本
        if sentence_buffer.strip():
            engine.tts.put_text(sentence_buffer.strip())
            logger.info(f"[Realtime] Sent final text to TTS: {sentence_buffer[:30]}...")
            
        logger.info(f"[Full Realtime Streaming] LLM complete: {len(full_response)} chars")
        
        # 3. 等待并推送所有视频帧
        from webrtc_streamer import get_webrtc_streamer
        streamer = get_webrtc_streamer()
        
        frame_count = 0
        # 持续读取视频帧直到引擎完成
        while True:
            try:
                video_frame = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: engine.video_frame_queue.get(timeout=3)
                    ),
                    timeout=5
                )
                
                await streamer.stream_frame(session_id, video_frame)
                frame_count += 1
                
                if frame_count == 1:
                    logger.info(f"⚡ First frame pushed!")
                    
                if frame_count % 25 == 0:
                    logger.info(f"Streamed {frame_count} frames")
                    
            except (asyncio.TimeoutError, Exception):
                if engine.video_frame_queue.empty():
                    break
                    
        logger.info(f"[Full Realtime Streaming] Complete: {frame_count} frames, {len(full_response)} chars")
        return full_response


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
