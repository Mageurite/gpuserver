import asyncio
import json
import logging
from typing import Optional, Dict
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status
from fastapi.responses import JSONResponse
import uvicorn

from config import settings
from session_manager import get_session_manager
from ai_models import get_ai_engine

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


# 活跃的 WebSocket 连接
active_connections: Dict[str, WebSocket] = {}


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "GPU Server WebSocket API",
        "active_connections": len(active_connections)
    }


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(..., description="engine_token for authentication")
):
    """
    WebSocket 实时对话接口

    Args:
        websocket: WebSocket 连接对象
        session_id: 会话 ID
        token: engine_token（用于验证）

    消息格式:
        客户端 -> 服务器:
            {
                "type": "text" | "audio",
                "content": "用户输入的文本",
                "data": "base64编码的音频数据"  # 仅 audio 类型需要
            }

        服务器 -> 客户端:
            {
                "type": "text" | "audio" | "transcription" | "error",
                "content": "AI 响应内容",
                "role": "assistant",
                "timestamp": "2024-01-01T12:00:00"
            }
    """
    manager = get_session_manager()

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
    active_connections[session_id] = websocket
    logger.info(f"WebSocket connected: session_id={session_id}, tutor_id={session.tutor_id}")

    # 发送欢迎消息
    await send_message(websocket, {
        "type": "text",
        "content": f"欢迎！您已连接到虚拟导师 (Tutor ID: {session.tutor_id})",
        "role": "assistant",
        "timestamp": datetime.now().isoformat()
    })

    try:
        # 获取 AI 引擎（按 tutor_id 隔离）
        ai_engine = get_ai_engine(session.tutor_id)

        # 消息处理循环
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            message = json.loads(data)

            # 更新会话活动时间
            manager.update_activity(session_id)

            # 处理消息
            await handle_message(websocket, session, message, ai_engine)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session_id={session_id}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        await send_error(websocket, "Invalid message format")
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
        await send_error(websocket, f"Internal server error: {str(e)}")
    finally:
        # 清理连接
        active_connections.pop(session_id, None)
        logger.info(f"Connection cleaned up: session_id={session_id}")


async def handle_message(websocket: WebSocket, session, message: dict, ai_engine):
    """
    处理客户端消息

    Args:
        websocket: WebSocket 连接
        session: 会话对象
        message: 客户端消息
        ai_engine: AI 引擎实例
    """
    msg_type = message.get("type")
    content = message.get("content", "")

    logger.info(f"Received message: session_id={session.session_id}, type={msg_type}")

    try:
        if msg_type == "text":
            # 处理文本消息
            avatar_id = message.get("avatar_id")  # 可选的 avatar_id

            # LLM: 生成响应
            response = await ai_engine.process_text(
                text=content,
                tutor_id=session.tutor_id,
                kb_id=session.kb_id
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
                logger.info(f"Sending video response: video_size={len(video_response)} bytes")
            else:
                logger.info("Sending audio-only response")

            # 发送响应
            logger.info(f"About to send response: type={response_message['type']}")
            await send_message(websocket, response_message)
            logger.info("Response sent successfully")

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
            response = await ai_engine.process_text(
                text=transcription,
                tutor_id=session.tutor_id,
                kb_id=session.kb_id
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
