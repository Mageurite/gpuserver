import asyncio
import json
import logging
import time
from typing import Optional, Dict
from datetime import datetime
import os
import cv2
import numpy as np

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status
from fastapi.responses import JSONResponse
import uvicorn

from config import settings
from session_manager import get_session_manager
from ai_models import get_ai_engine
from webrtc_streamer import get_webrtc_streamer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# FastAPI 应用
app = FastAPI(
    title="GPU Server WebSocket API",
    description="AI 推理引擎实时对话接口",
    version="1.0.0"
)


# 活跃的 WebSocket 连接（按 connection_id 索引）
active_connections: Dict[str, WebSocket] = {}

# Session 上下文管理（按 engine_session_id 索引）
# 用于存储每个 session 的上下文信息（对话历史、状态等）
session_contexts: Dict[str, dict] = {}


async def load_idle_frames(avatar_id: str) -> list:
    """
    Load idle video frames for WebRTC streaming

    Args:
        avatar_id: Avatar identifier

    Returns:
        List of numpy arrays (frames)
    """
    try:
        # 获取 avatar 目录
        avatar_dir = f"/workspace/gpuserver/data/avatars/{avatar_id}"

        if not os.path.exists(avatar_dir):
            logger.warning(f"Avatar directory not found: {avatar_dir}")
            return []

        # 尝试从 full_imgs 子目录加载
        full_imgs_dir = os.path.join(avatar_dir, "full_imgs")
        if os.path.exists(full_imgs_dir):
            search_dir = full_imgs_dir
        else:
            search_dir = avatar_dir

        # 读取所有帧
        frames = []
        frame_files = sorted([f for f in os.listdir(search_dir) if f.endswith('.png')])

        # 只加载前 125 帧（5秒 @ 25fps）
        for frame_file in frame_files[:125]:
            frame_path = os.path.join(search_dir, frame_file)
            frame = cv2.imread(frame_path)
            if frame is not None:
                frames.append(frame)

        logger.info(f"Loaded {len(frames)} idle frames for avatar {avatar_id} from {search_dir}")
        return frames

    except Exception as e:
        logger.error(f"Failed to load idle frames: {e}")
        return []


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "GPU Server WebSocket API",
        "active_connections": len(active_connections)
    }


@app.websocket("/ws/{connection_id}")
@app.websocket("/ws/ws/{connection_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    connection_id: str,
    token: Optional[str] = Query(None, description="engine_token or auth_token for authentication (optional)")
):
    """
    WebSocket 实时对话接口

    Args:
        websocket: WebSocket 连接对象
        connection_id: 连接标识符（可以是 session_id 或 user_{user_id}）
        token: engine_token（用于验证）

    连接模式:
        1. 新模式（基于 user_id）: connection_id = "user_{user_id}"
           - 同一个 user_id 的所有 session 共享一个 WebSocket 连接
           - 支持两种子模式：
             a) 有 session 模式：提供 token，可以使用 engine_session_id 路由
             b) 无 session 模式：不提供 token，每条消息必须包含 tutor_id

        2. 旧模式（基于 session_id）: connection_id = "{session_id}"
           - 每个 session 独立的 WebSocket 连接（向后兼容）
           - 必须提供 token

    消息格式:
        客户端 -> 服务器:
            {
                "type": "text_webrtc" | "text" | "audio" | "webrtc_offer" | "webrtc_ice_candidate",
                "content": "用户输入的文本",
                "tutor_id": 1,  # 必需，用于选择 Avatar 视频
                "session_id": 59,  # 可选，用于区分聊天历史
                "engine_session_id": "uuid-here",  # 有 session 模式可选
                "user_id": 123,  # WebRTC 相关消息必需
                "avatar_id": "avatar_tutor_13",  # 可选
                "kb_id": "knowledge_base_id"  # 可选
            }

        说明：
            - tutor_id: 控制使用哪个 Avatar 视频（同一个 tutor 的所有学生共享同一个 Avatar）
            - session_id: 控制聊天历史存储位置（同一个学生可以有多个 session）
            - 视频按 tutor_id 区分，聊天记录按 session_id 区分

        服务器 -> 客户端:
            {
                "type": "text" | "audio" | "video" | "transcription" | "error",
                "content": "AI 响应内容",
                "role": "assistant",
                "timestamp": "2024-01-01T12:00:00"
            }
    """
    manager = get_session_manager()

    # 判断连接模式
    is_user_based = connection_id.startswith("user_")

    if is_user_based:
        # 新模式：基于 user_id
        user_id = connection_id.replace("user_", "")
        logger.info(f"User-based connection mode: user_id={user_id}, token_provided={token is not None}")

        # Session 是可选的
        session = None

        if token:
            # 如果提供了 token，尝试验证并获取 session
            verified_session_id = manager.verify_token(token)
            if verified_session_id:
                session = manager.get_session(verified_session_id)
                logger.info(f"Token verified, using session: {verified_session_id}")
            else:
                logger.warning(f"Invalid token provided, will use sessionless mode")
        else:
            logger.info(f"No token provided, using sessionless mode")

        # 接受连接（无论是否有 session）
        await websocket.accept()
        active_connections[connection_id] = websocket
        logger.info(f"WebSocket connected (user-based): connection_id={connection_id}, user_id={user_id}, has_session={session is not None}")

    else:
        # 旧模式：基于 session_id（向后兼容）
        session_id = connection_id
        logger.info(f"Session-based connection mode: session_id={session_id}")

        # 验证 token
        verified_session_id = manager.verify_token(token)
        if not verified_session_id or verified_session_id != session_id:
            logger.warning(f"Invalid token for session {session_id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # 获取会话信息
        session = manager.get_session(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # 接受连接
        await websocket.accept()
        active_connections[connection_id] = websocket
        logger.info(f"WebSocket connected (session-based): session_id={session_id}, tutor_id={session.tutor_id}")

    # 获取 AI 引擎（按 tutor_id 隔离）
    # 在 user-based 无 session 模式下，ai_engine 会在第一条消息时创建
    ai_engine = None
    if session:
        ai_engine = get_ai_engine(session.tutor_id)
        logger.info(f"AI engine initialized for tutor_id={session.tutor_id}")

        # 预热 subprocess 推理引擎（异步，不阻塞）
        # 使用 ai_engine 中的 avatar_manager 实例，确保复用同一个引擎
        avatar_id = f"avatar_tutor_{session.tutor_id}"
        try:
            if hasattr(ai_engine, 'avatar_manager') and ai_engine.avatar_manager:
                ai_engine.avatar_manager.warmup_subprocess_engine(avatar_id)
            else:
                logger.warning(f"AI engine does not have avatar_manager, skipping warmup")
        except Exception as e:
            logger.warning(f"Failed to warmup subprocess engine for {avatar_id}: {e}")

    # 自动发送待机视频（如果启用了 Avatar）
    # 注意：在 user-based 模式下，可能需要等待第一条消息来确定 avatar_id
    if settings.enable_avatar and not is_user_based and session:
        # 只在 session-based 模式下自动发送待机视频
        avatar_id = f"avatar_tutor_{session.tutor_id}"
        logger.info(f"Auto-sending idle video for avatar_id={avatar_id}")

        try:
            video_response = await ai_engine.get_idle_video(
                avatar_id=avatar_id,
                duration=5,  # 5秒循环视频
                fps=25
            )

            if video_response:
                await send_message(websocket, {
                    "type": "video",
                    "content": "",  # 待机视频没有文本内容
                    "video": video_response,
                    "role": "assistant",
                    "timestamp": datetime.now().isoformat()
                })
                logger.info(f"Idle video sent automatically: video_size={len(video_response)} bytes")
            else:
                logger.warning("Failed to get idle video, skipping auto-send")
        except Exception as e:
            logger.error(f"Error auto-sending idle video: {e}", exc_info=True)
    elif not is_user_based and session:
        # 如果没有启用 Avatar，发送欢迎消息（仅 session-based 模式）
        await send_message(websocket, {
            "type": "text",
            "content": f"欢迎！您已连接到虚拟导师 (Tutor ID: {session.tutor_id})",
            "role": "assistant",
            "timestamp": datetime.now().isoformat()
        })

    try:
        # 消息处理循环
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            message = json.loads(data)

            # 在 user-based 模式下，从消息中获取 engine_session_id（可选）
            if is_user_based:
                # 无 session 模式：从消息中获取 tutor_id
                if not session:
                    tutor_id = message.get("tutor_id")
                    if not tutor_id:
                        await send_error(websocket, "tutor_id is required in sessionless mode")
                        continue

                    # 动态创建 AI 引擎
                    if not ai_engine:
                        ai_engine = get_ai_engine(tutor_id)
                        logger.info(f"AI engine created dynamically for tutor_id={tutor_id}")

                        # 预热 subprocess 推理引擎（异步，不阻塞）
                        # 使用 ai_engine 中的 avatar_manager 实例，确保复用同一个引擎
                        avatar_id = f"avatar_tutor_{tutor_id}"
                        try:
                            if hasattr(ai_engine, 'avatar_manager') and ai_engine.avatar_manager:
                                ai_engine.avatar_manager.warmup_subprocess_engine(avatar_id)
                            else:
                                logger.warning(f"AI engine does not have avatar_manager, skipping warmup")
                        except Exception as e:
                            logger.warning(f"Failed to warmup subprocess engine for {avatar_id}: {e}")

                    # 直接处理消息（无 session）
                    await handle_message(websocket, None, message, ai_engine, is_user_based)
                else:
                    # 有 session 模式
                    engine_session_id = message.get("engine_session_id")

                    # 如果没有提供 engine_session_id，使用默认的 session（连接时验证的那个）
                    if not engine_session_id:
                        engine_session_id = session.session_id
                        logger.info(f"No engine_session_id provided, using default session: {engine_session_id}")

                    # 获取或创建 session 上下文
                    if engine_session_id not in session_contexts:
                        # 验证 engine_session_id 是否有效
                        target_session = manager.get_session(engine_session_id)
                        if not target_session:
                            await send_error(websocket, f"Invalid engine_session_id: {engine_session_id}")
                            continue

                        # 创建 session 上下文
                        session_contexts[engine_session_id] = {
                            "session": target_session,
                            "ai_engine": get_ai_engine(target_session.tutor_id)
                        }
                        logger.info(f"Created session context for engine_session_id={engine_session_id}")

                    # 更新会话活动时间
                    manager.update_activity(engine_session_id)

                    # 处理消息（使用 engine_session_id 对应的 session）
                    ctx = session_contexts[engine_session_id]
                    await handle_message(websocket, ctx["session"], message, ctx["ai_engine"], is_user_based)

            else:
                # 旧模式：使用 connection_id 作为 session_id
                session_id = connection_id
                manager.update_activity(session_id)
                await handle_message(websocket, session, message, ai_engine, is_user_based)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: connection_id={connection_id}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        await send_error(websocket, "Invalid message format")
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
        await send_error(websocket, f"Internal server error: {str(e)}")
    finally:
        # 清理连接
        active_connections.pop(connection_id, None)

        # 在 user-based 模式下，清理该用户的所有 session 上下文
        if is_user_based:
            # 注意：这里不清理 session_contexts，因为用户可能会重新连接
            # session_contexts 会在 session 过期时自动清理
            logger.info(f"Connection cleaned up (user-based): connection_id={connection_id}")
        else:
            logger.info(f"Connection cleaned up (session-based): connection_id={connection_id}")


async def stream_audio_video(
    ai_engine,
    text: str,
    avatar_id: str,
    user_id: int,
    websocket: WebSocket
):
    """
    并行处理音视频生成和推送（逐帧流式）
    
    架构（参考 virtual-tutor）:
    1. TTS 生成音频
    2. MuseTalk realtime_engine 生成帧 → res_frame_queue
    3. process_frames 线程: res_frame_queue → video_track.frame_queue
    4. WebRTC track.recv(): frame_queue → 客户端
    
    Args:
        ai_engine: AI 引擎实例
        text: 完整文本
        avatar_id: Avatar ID
        user_id: 用户 ID
        websocket: WebSocket 连接（用于错误通知）
    """
    try:
        streamer = get_webrtc_streamer()
        session_id = f"user_{user_id}"
        
        # 获取 video_track（WebRTC track）
        if session_id not in streamer.video_tracks:
            logger.error(f"No video track found for session {session_id}")
            await send_error(websocket, "WebRTC connection not established")
            return
        
        video_track = streamer.video_tracks[session_id]
        
        # ====== 阶段2: TTS 生成（完整音频）======
        logger.info(f"[Pipeline] Stage 2: TTS generation...")
        audio_data = await ai_engine.synthesize_speech(text)
        logger.info(f"[Pipeline] Stage 2 complete: audio_length={len(audio_data)}")
        
        # ====== 阶段3: 启动 realtime_engine 生成帧到 res_frame_queue ======
        logger.info(f"[Pipeline] Stage 3: Starting realtime frame generation...")
        
        # 先启动视频生成，等第一帧出现后再启动音频（实现音视频同步）
        audio_task = None
        audio_started = False
        
        frame_count = 0
        async for frame in ai_engine.video_engine.generate_frames_stream(
            audio_data=audio_data, avatar_id=avatar_id, fps=25
        ):
            # 在推送第一帧视频时，同时启动音频推送（实现音视频同步）
            if not audio_started:
                audio_task = asyncio.create_task(
                    streamer.stream_audio(session_id, audio_data)
                )
                audio_started = True
                logger.info(f"[Pipeline] 🔊 Audio streaming started (synchronized with first video frame)")
            
            # 直接将帧推送到 video_track 的 frame_queue
            await video_track.frame_queue.put(frame)
            frame_count += 1
            if frame_count == 1:
                logger.info(f"[Pipeline] ⚡ First frame pushed to WebRTC queue")
            if frame_count % 20 == 0:
                logger.info(f"[Pipeline] 📤 Pushed {frame_count} frames to WebRTC (qsize={video_track.frame_queue.qsize()})")
        
        logger.info(f"[Pipeline] Stage 3 complete: {frame_count} frames generated")
        
        # 等待音频完成
        if audio_task:
            await audio_task
        logger.info(f"[Pipeline] ✅ Complete: {frame_count} frames, audio delivered")
        
    except Exception as e:
        logger.error(f"[Pipeline] ❌ Failed: {e}", exc_info=True)
        await send_error(websocket, f"Processing failed: {str(e)}")


async def handle_message(websocket: WebSocket, session, message: dict, ai_engine, is_user_based: bool = False):
    """
    处理客户端消息

    Args:
        websocket: WebSocket 连接
        session: 会话对象（可以为 None，在 sessionless 模式下）
        message: 客户端消息
        ai_engine: AI 引擎实例
        is_user_based: 是否为 user-based 模式
    """
    msg_type = message.get("type")
    content = message.get("content", "")

    session_id = session.session_id if session else "sessionless"
    logger.info(f"Received message: session_id={session_id}, type={msg_type}")

    try:
        if msg_type == "init":
            # 处理初始化消息 - 返回待机视频（idle video）
            avatar_id = message.get("avatar_id")  # 必需的 avatar_id

            if not avatar_id:
                await send_error(websocket, "avatar_id is required for init message")
                return

            logger.info(f"Processing init message: avatar_id={avatar_id}")

            # 获取待机视频（不生成 TTS，只返回循环的静态视频）
            video_response = None
            if settings.enable_avatar:
                logger.info(f"Getting idle video for avatar_id={avatar_id}")
                video_response = await ai_engine.get_idle_video(
                    avatar_id=avatar_id,
                    duration=5,  # 5秒循环视频
                    fps=25
                )

            if video_response:
                # 构建响应消息 - 只包含视频，不包含音频和文本
                response_message = {
                    "type": "video",
                    "content": "",  # 待机视频没有文本内容
                    "video": video_response,  # base64 编码的视频
                    "role": "assistant",
                    "timestamp": datetime.now().isoformat()
                }
                logger.info(f"Sending idle video: video_size={len(video_response)} bytes")
            else:
                # 如果无法获取待机视频，返回错误
                await send_error(websocket, "Failed to get idle video")
                return

            # 发送响应
            await send_message(websocket, response_message)
            logger.info("Idle video sent successfully")

        elif msg_type == "text_webrtc":
            # 处理文本消息 - WebRTC 实时流式传输模式（三阶段流式 Pipeline）
            avatar_id = message.get("avatar_id")  # 必需的 avatar_id
            user_id = message.get("user_id")  # 前端传入的 user_id
            engine_session_id = message.get("engine_session_id")  # 用于路由的 session_id

            if not avatar_id:
                await send_error(websocket, "avatar_id is required for WebRTC streaming")
                return

            if not user_id:
                await send_error(websocket, "user_id is required for WebRTC streaming")
                return

            # 获取 tutor_id、kb_id 和 session_id（从 session 或消息中）
            tutor_id = session.tutor_id if session else message.get("tutor_id")
            kb_id = session.kb_id if session else message.get("kb_id")
            session_id_for_chat = message.get("session_id")  # 用于区分聊天历史

            # 在 user-based 模式下，engine_session_id 应该已经在外层处理
            # 这里记录日志以便调试
            session_id_log = session.session_id if session else "sessionless"
            logger.info(f"Processing text with WebRTC streaming: avatar_id={avatar_id}, user_id={user_id}, engine_session_id={engine_session_id}, session_id={session_id_log}")

            # 记录开始时间
            start_time = time.time()

            # ====== 阶段1: LLM 流式生成 ======
            full_text = ""
            first_token_time = None

            async for token in ai_engine.stream_text_response(
                text=content, tutor_id=tutor_id, kb_id=kb_id, session_id=session_id_for_chat
            ):
                # 记录首 token 时间
                if first_token_time is None:
                    first_token_time = time.time()
                    logger.info(f"⚡ First token: {first_token_time - start_time:.2f}s")

                # 立即发送 token
                await send_message(websocket, {
                    "type": "text_stream",
                    "token": token,
                    "role": "assistant",
                    "timestamp": datetime.now().isoformat()
                })
                
                # 调试：记录发送
                if first_token_time is not None and (time.time() - first_token_time) < 0.1:
                    logger.info(f"📤 Sent first text_stream token: {token[:20]}...")

                full_text += token

            # 发送完成信号
            await send_message(websocket, {
                "type": "text_complete",
                "content": full_text,
                "role": "assistant",
                "timestamp": datetime.now().isoformat()
            })

            text_complete_time = time.time()
            logger.info(f"Text complete: {text_complete_time - start_time:.2f}s")

            # 发送状态消息，告知前端音视频生成已启动
            await send_message(websocket, {
                "type": "processing_status",
                "status": "generating_audio_video",
                "message": "正在生成音视频...",
                "timestamp": datetime.now().isoformat()
            })

            # ====== 阶段2+3: 音视频异步处理 ======
            asyncio.create_task(
                stream_audio_video(ai_engine, full_text, avatar_id, user_id, websocket)
            )

            logger.info("WebRTC streaming response initiated (audio + video via WebRTC)")

        elif msg_type == "text":
            # 处理文本消息 - 流式响应模式（立即发送文本）
            avatar_id = message.get("avatar_id")  # 可选的 avatar_id
            user_id = message.get("user_id")  # 用户 ID (用于 WebRTC 音频)

            # 获取 tutor_id、kb_id 和 session_id（从 session 或消息中）
            tutor_id = session.tutor_id if session else message.get("tutor_id")
            kb_id = session.kb_id if session else message.get("kb_id")
            session_id_for_chat = message.get("session_id")  # 用于区分聊天历史

            # 1. LLM: 生成响应
            response = await ai_engine.process_text(
                text=content,
                tutor_id=tutor_id,
                kb_id=kb_id,
                session_id=session_id_for_chat  # 传递 session_id 用于聊天历史
            )

            # 2. 立即发送文本响应
            await send_message(websocket, {
                "type": "text",
                "content": response,
                "role": "assistant",
                "timestamp": datetime.now().isoformat()
            })
            logger.info("Text response sent immediately")

            # 3. TTS: 文本转语音
            audio_response = await ai_engine.synthesize_speech(response)

            # 4. 发送音频 (通过 WebRTC 或 WebSocket,取决于是否有 user_id)
            if user_id:
                # 通过 WebRTC 发送音频（使用全局导入的 get_webrtc_streamer）
                streamer = get_webrtc_streamer()
                asyncio.create_task(streamer.stream_audio(f"user_{user_id}", audio_response))
                logger.info(f"Audio sent via WebRTC for user {user_id}")
            else:
                # 回退到 WebSocket 发送音频 (向后兼容)
                await send_message(websocket, {
                    "type": "audio",
                    "content": response,
                    "audio": audio_response,  # base64 编码的音频
                    "role": "assistant",
                    "timestamp": datetime.now().isoformat()
                })
                logger.info("Audio response sent via WebSocket (no user_id provided)")

            # 5. 可选：后台生成视频（不阻塞）
            if settings.enable_avatar and avatar_id:
                logger.info(f"Starting background video generation for avatar_id={avatar_id}")

                # 在后台异步生成视频
                async def generate_video_background():
                    try:
                        video_response = await ai_engine.generate_video(
                            audio_data=audio_response,
                            avatar_id=avatar_id,
                            fps=25
                        )

                        if video_response:
                            # 视频生成完成后发送
                            await send_message(websocket, {
                                "type": "video",
                                "content": response,
                                "video": video_response,
                                "role": "assistant",
                                "timestamp": datetime.now().isoformat()
                            })
                            logger.info(f"Background video sent: video_size={len(video_response)} bytes")
                    except Exception as e:
                        logger.error(f"Background video generation failed: {e}")

                # 启动后台任务（不等待）
                asyncio.create_task(generate_video_background())

        elif msg_type == "audio":
            # 处理音频消息
            audio_data = message.get("data", "")
            avatar_id = message.get("avatar_id")  # 可选的 avatar_id

            logger.info(f"Audio message received: avatar_id={avatar_id}, enable_avatar={settings.enable_avatar}")

            # ASR: 音频转文本
            transcription = await ai_engine.process_audio(audio_data)

            # 发送转录结果
            await send_message(websocket, {
                "type": "transcription",
                "content": transcription,
                "role": "user",
                "timestamp": datetime.now().isoformat()
            })

            # LLM: 生成响应
            tutor_id = session.tutor_id if session else message.get("tutor_id")
            kb_id = session.kb_id if session else message.get("kb_id")
            session_id_for_chat = message.get("session_id")  # 用于区分聊天历史

            response = await ai_engine.process_text(
                text=transcription,
                tutor_id=tutor_id,
                kb_id=kb_id,
                session_id=session_id_for_chat  # 传递 session_id 用于聊天历史
            )

            # TTS: 文本转语音
            audio_response = await ai_engine.synthesize_speech(response)

            # 如果启用了 Avatar 且提供了 avatar_id，生成视频
            video_response = None
            if settings.enable_avatar and avatar_id:
                logger.info(f"Generating video for avatar_id={avatar_id}")
                video_response = await ai_engine.generate_video(
                    audio_data=audio_response,
                    avatar_id=avatar_id,
                    fps=25
                )

            # 构建响应消息
            response_message = {
                "type": "video" if video_response else "audio",
                "content": response,
                "audio": audio_response,  # base64 编码的音频
                "role": "assistant",
                "timestamp": datetime.now().isoformat()
            }

            # 如果有视频，添加视频数据
            if video_response:
                response_message["video"] = video_response  # base64 编码的视频

            # 发送响应
            await send_message(websocket, response_message)

        elif msg_type == "webrtc_offer":
            # 处理 WebRTC offer
            offer_sdp = message.get("sdp")
            user_id = message.get("user_id")  # 前端传入的 user_id
            avatar_id = message.get("avatar_id", "avatar_tutor_13")  # 可选的 avatar_id

            if not offer_sdp:
                await send_error(websocket, "SDP offer is required")
                return

            if not user_id:
                await send_error(websocket, "user_id is required for WebRTC")
                return

            session_id_log = session.session_id if session else "sessionless"
            logger.info(f"Received WebRTC offer from session {session_id_log}, user_id={user_id}")

            # 获取 WebRTC streamer
            webrtc_streamer = get_webrtc_streamer()

            # 加载待机视频帧
            idle_frames = await load_idle_frames(avatar_id)

            # 处理 offer 并生成 answer（使用 user_id，同一用户共享）
            # 传递 websocket 以便发送 ICE candidates
            answer_sdp = await webrtc_streamer.handle_offer(
                session_id=f"user_{user_id}",  # 使用 user_id 作为标识
                offer_sdp=offer_sdp,
                idle_frames=idle_frames,  # 传入待机帧
                websocket=websocket  # 传入 WebSocket 连接
            )

            # 发送 answer 回客户端
            await send_message(websocket, {
                "type": "webrtc_answer",
                "sdp": answer_sdp,
                "timestamp": datetime.now().isoformat()
            })

            logger.info(f"WebRTC answer sent to user {user_id} with idle frames")

        elif msg_type == "webrtc_ice_candidate":
            # 处理 ICE candidate
            candidate = message.get("candidate")
            user_id = message.get("user_id")  # 前端传入的 user_id

            if not candidate:
                await send_error(websocket, "ICE candidate is required")
                return

            if not user_id:
                await send_error(websocket, "user_id is required for WebRTC")
                return

            session_id_log = session.session_id if session else "sessionless"
            logger.info(f"Received ICE candidate from session {session_id_log}, user_id={user_id}")

            # 获取 WebRTC streamer
            webrtc_streamer = get_webrtc_streamer()

            # 添加 ICE candidate（使用 user_id）
            await webrtc_streamer.add_ice_candidate(
                session_id=f"user_{user_id}",  # 使用 user_id 作为标识
                candidate=candidate
            )

        else:
            await send_error(websocket, f"Unsupported message type: {msg_type}")

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await send_error(websocket, f"Failed to process message: {str(e)}")


async def send_message(websocket: WebSocket, message: dict):
    """发送消息给客户端"""
    try:
        await websocket.send_json(message)
    except Exception as e:
        logger.error(f"Failed to send message: {e}")


async def send_error(websocket: WebSocket, error: str):
    """发送错误消息"""
    await send_message(websocket, {
        "type": "error",
        "content": error,
        "timestamp": datetime.now().isoformat()
    })


def main():
    """启动 WebSocket 服务"""
    uvicorn.run(
        app,
        host=settings.websocket_host,
        port=settings.websocket_port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
