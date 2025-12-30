"""
简化版 GPU Server WebSocket 服务
移除了对 aiortc、cv2 等重依赖的要求
保留完整的 token 验证和 WebSocket 连接逻辑
"""
import asyncio
import json
import logging
from typing import Optional, Dict
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status
from fastapi.responses import JSONResponse
import uvicorn

# 尝试导入，如果失败则使用简化版本
try:
    from config import settings
except ImportError:
    # 简化的配置
    class Settings:
        websocket_host = "0.0.0.0"
        websocket_port = 19001
        enable_avatar = False
    settings = Settings()

try:
    from session_manager import get_session_manager
except ImportError:
    # 简化的 session manager
    class SimpleSessionManager:
        def __init__(self):
            self.sessions = {}
            self.tokens = {}

        def verify_token(self, token: str) -> Optional[str]:
            """验证 token 并返回 session_id"""
            # 简化版：接受任何非空 token
            if token and len(token) > 0:
                # 返回一个默认的 session_id
                return "default_session"
            return None

        def get_session(self, session_id: str):
            """获取 session 信息"""
            # 返回一个简化的 session 对象
            class SimpleSession:
                def __init__(self):
                    self.session_id = session_id
                    self.tutor_id = 13
                    self.kb_id = None
            return SimpleSession()

        def update_activity(self, session_id: str):
            """更新活动时间"""
            pass

    _session_manager = SimpleSessionManager()

    def get_session_manager():
        return _session_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI 应用
app = FastAPI(
    title="GPU Server WebSocket API (Simplified)",
    description="简化版 AI 推理引擎实时对话接口",
    version="1.0.0-simplified"
)

# 活跃的 WebSocket 连接（按 connection_id 索引）
active_connections: Dict[str, WebSocket] = {}

# Session 上下文管理（按 engine_session_id 索引）
session_contexts: Dict[str, dict] = {}


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "GPU Server WebSocket API (Simplified)",
        "active_connections": len(active_connections),
        "session_contexts": len(session_contexts)
    }


@app.websocket("/ws/{connection_id}")
@app.websocket("/ws/ws/{connection_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    connection_id: str,
    token: str = Query(..., description="engine_token for authentication")
):
    """
    WebSocket 实时对话接口

    支持两种连接模式:
        1. User-based: connection_id = "user_{user_id}"
        2. Session-based: connection_id = "{session_id}"
    """
    manager = get_session_manager()

    # 判断连接模式
    is_user_based = connection_id.startswith("user_")

    if is_user_based:
        # 新模式：基于 user_id
        user_id = connection_id.replace("user_", "")
        logger.info(f"User-based connection mode: user_id={user_id}, token={token[:20]}...")

        # 验证 token
        verified_session_id = manager.verify_token(token)
        if not verified_session_id:
            logger.warning(f"Invalid token for user {user_id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # 获取 session 信息
        session = manager.get_session(verified_session_id)
        if not session:
            logger.warning(f"Session {verified_session_id} not found")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # 接受连接
        await websocket.accept()
        active_connections[connection_id] = websocket
        logger.info(f"✅ WebSocket connected (user-based): connection_id={connection_id}, user_id={user_id}")

    else:
        # 旧模式：基于 session_id
        session_id = connection_id
        logger.info(f"Session-based connection mode: session_id={session_id}, token={token[:20]}...")

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
        logger.info(f"✅ WebSocket connected (session-based): session_id={session_id}")

    # 发送欢迎消息
    await send_message(websocket, {
        "type": "connection_success",
        "connection_id": connection_id,
        "mode": "user-based" if is_user_based else "session-based",
        "message": f"Connected to GPU Server (Simplified)",
        "timestamp": datetime.now().isoformat()
    })

    try:
        # 消息处理循环
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            message = json.loads(data)

            # 在 user-based 模式下，从消息中获取 engine_session_id
            if is_user_based:
                engine_session_id = message.get("engine_session_id")
                if not engine_session_id and message.get("type") not in ["webrtc_offer", "webrtc_ice_candidate"]:
                    await send_error(websocket, "engine_session_id is required in user-based mode")
                    continue

                # 获取或创建 session 上下文
                if engine_session_id and engine_session_id not in session_contexts:
                    target_session = manager.get_session(engine_session_id)
                    if not target_session:
                        await send_error(websocket, f"Invalid engine_session_id: {engine_session_id}")
                        continue

                    session_contexts[engine_session_id] = {
                        "session": target_session,
                        "created_at": datetime.now().isoformat()
                    }
                    logger.info(f"Created session context for engine_session_id={engine_session_id}")

                # 更新会话活动时间
                if engine_session_id:
                    manager.update_activity(engine_session_id)

                # 处理消息
                if engine_session_id and engine_session_id in session_contexts:
                    ctx = session_contexts[engine_session_id]
                    await handle_message(websocket, ctx["session"], message, is_user_based)
                elif message.get("type") in ["webrtc_offer", "webrtc_ice_candidate"]:
                    await handle_message(websocket, session, message, is_user_based)
                else:
                    await send_error(websocket, f"Session context not found: {engine_session_id}")

            else:
                # 旧模式：使用 connection_id 作为 session_id
                session_id = connection_id
                manager.update_activity(session_id)
                await handle_message(websocket, session, message, is_user_based)

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
        logger.info(f"Connection cleaned up: connection_id={connection_id}")


async def handle_message(websocket: WebSocket, session, message: dict, is_user_based: bool = False):
    """处理客户端消息"""
    msg_type = message.get("type")
    content = message.get("content", "")

    logger.info(f"📨 Received message: session_id={session.session_id}, type={msg_type}")

    try:
        if msg_type == "text_webrtc":
            # 处理文本消息 - WebRTC 模式
            avatar_id = message.get("avatar_id")
            user_id = message.get("user_id")
            engine_session_id = message.get("engine_session_id")

            if not avatar_id:
                await send_error(websocket, "avatar_id is required for WebRTC streaming")
                return

            if not user_id:
                await send_error(websocket, "user_id is required for WebRTC streaming")
                return

            logger.info(f"Processing text_webrtc: avatar_id={avatar_id}, user_id={user_id}, engine_session_id={engine_session_id}")

            # 简化版：直接返回模拟响应
            response_text = f"[简化版] 收到消息: {content}"

            await send_message(websocket, {
                "type": "text",
                "content": response_text,
                "audio": None,  # 简化版不生成音频
                "role": "assistant",
                "timestamp": datetime.now().isoformat()
            })

            logger.info("✅ Response sent")

        elif msg_type == "text":
            # 处理普通文本消息
            logger.info(f"Processing text: {content}")

            response_text = f"[简化版] 收到消息: {content}"

            await send_message(websocket, {
                "type": "text",
                "content": response_text,
                "role": "assistant",
                "timestamp": datetime.now().isoformat()
            })

            logger.info("✅ Response sent")

        elif msg_type == "webrtc_offer":
            # 处理 WebRTC offer
            user_id = message.get("user_id")
            avatar_id = message.get("avatar_id", "avatar_tutor_13")

            if not user_id:
                await send_error(websocket, "user_id is required for WebRTC")
                return

            logger.info(f"Received WebRTC offer from user_id={user_id}")

            # 简化版：返回模拟的 answer
            await send_message(websocket, {
                "type": "webrtc_answer",
                "sdp": "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n",
                "timestamp": datetime.now().isoformat()
            })

            logger.info(f"✅ WebRTC answer sent to user {user_id}")

        elif msg_type == "webrtc_ice_candidate":
            # 处理 ICE candidate
            user_id = message.get("user_id")

            if not user_id:
                await send_error(websocket, "user_id is required for WebRTC")
                return

            logger.info(f"Received ICE candidate from user_id={user_id}")
            # 简化版：不做实际处理

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
    logger.info("🚀 Starting Simplified GPU Server...")
    logger.info(f"📍 Host: {settings.websocket_host}")
    logger.info(f"📍 Port: {settings.websocket_port}")
    logger.info("⚠️  This is a simplified version without AI capabilities")

    uvicorn.run(
        app,
        host=settings.websocket_host,
        port=settings.websocket_port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
