#!/usr/bin/env python3
"""
GPU Server - 统一服务器
同时提供管理 API 和 WebSocket 服务
"""

import asyncio
import json
import logging
import uuid
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
    title="GPU Server",
    description="AI 推理引擎 - 管理 API 和 WebSocket 服务",
    version="1.0.0"
)

# 添加 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 活跃的 WebSocket 连接
active_connections = {}


# ===== 数据模型 =====

class CreateSessionRequest(BaseModel):
    tutor_id: int
    student_id: int
    kb_id: Optional[str] = None


# ===== 管理 API 路由 =====

@app.get("/health")
async def health_check():
    """健康检查"""
    manager = get_session_manager()
    return {
        "status": "healthy",
        "service": "GPU Server Management API",
        "active_sessions": len(manager.get_all_sessions()),
        "max_sessions": settings.max_sessions
    }


@app.post("/v1/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(request: CreateSessionRequest):
    """创建新会话"""
    manager = get_session_manager()

    try:
        session = manager.create_session(
            tutor_id=request.tutor_id,
            student_id=request.student_id,
            kb_id=request.kb_id
        )

        # 构建 WebSocket URL
        engine_url = f"{settings.websocket_url}/ws/{session.session_id}"

        logger.info(f"Session created: {session.session_id} for tutor {request.tutor_id}")

        return {
            "session_id": session.session_id,
            "engine_url": engine_url,
            "engine_token": session.engine_token,
            "status": session.status
        }

    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )


@app.get("/v1/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    manager = get_session_manager()
    session = manager.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )

    return session.to_dict()


@app.delete("/v1/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str):
    """删除会话"""
    manager = get_session_manager()

    if not manager.delete_session(session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )

    logger.info(f"Session deleted: {session_id}")


@app.get("/v1/sessions")
async def list_sessions():
    """列出所有会话（调试用）"""
    manager = get_session_manager()
    sessions = manager.get_all_sessions()

    return {
        "total": len(sessions),
        "sessions": [session.to_dict() for session in sessions.values()]
    }


# ===== WebSocket 路由 =====

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(..., description="engine_token for authentication")
):
    """WebSocket 实时对话接口"""
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
    """处理客户端消息"""
    msg_type = message.get("type")
    content = message.get("content", "")

    logger.info(f"Received message: session_id={session.session_id}, type={msg_type}")

    try:
        if msg_type == "text":
            # 处理文本消息
            response = await ai_engine.process_text(
                text=content,
                tutor_id=session.tutor_id,
                kb_id=session.kb_id
            )

            # 发送文本响应
            await send_message(websocket, {
                "type": "text",
                "content": response,
                "role": "assistant",
                "timestamp": datetime.now().isoformat()
            })

        elif msg_type == "audio":
            # 处理音频消息
            audio_data = message.get("data", "")

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

            # 发送音频响应
            await send_message(websocket, {
                "type": "audio",
                "content": response,
                "data": audio_response,
                "role": "assistant",
                "timestamp": datetime.now().isoformat()
            })

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
    """启动服务"""
    print("=" * 60)
    print("GPU Server - Unified Mode")
    print("=" * 60)
    print(f"\nManagement API: http://0.0.0.0:{settings.management_api_port}")
    print(f"WebSocket API: ws://0.0.0.0:{settings.management_api_port}/ws")
    print(f"API Docs: http://0.0.0.0:{settings.management_api_port}/docs")
    print(f"\nMax Sessions: {settings.max_sessions}")
    print(f"Session Timeout: {settings.session_timeout_seconds}s")
    print("\n" + "=" * 60 + "\n")

    uvicorn.run(
        app,
        host=settings.management_api_host,
        port=settings.management_api_port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
