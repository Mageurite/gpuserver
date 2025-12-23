from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import uvicorn

from config import settings
from session_manager import get_session_manager


# Pydantic 模型
class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    tutor_id: int
    student_id: int
    kb_id: Optional[str] = None


class CreateSessionResponse(BaseModel):
    """创建会话响应"""
    session_id: str
    engine_url: str
    engine_token: str
    status: str


class SessionStatusResponse(BaseModel):
    """会话状态响应"""
    session_id: str
    tutor_id: int
    student_id: int
    kb_id: Optional[str]
    status: str
    created_at: str
    last_activity: str


# FastAPI 应用
app = FastAPI(
    title="GPU Server Management API",
    description="AI 推理引擎管理接口",
    version="1.0.0"
)


@app.get("/health")
async def health_check():
    """
    健康检查接口

    Returns:
        dict: 服务健康状态
    """
    manager = get_session_manager()
    active_sessions = len(manager.get_all_sessions())

    return {
        "status": "healthy",
        "service": "GPU Server Management API",
        "active_sessions": active_sessions,
        "max_sessions": settings.max_sessions
    }


@app.post("/v1/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(request: CreateSessionRequest):
    """
    创建新会话

    Args:
        request: 创建会话请求

    Returns:
        CreateSessionResponse: 会话信息，包含 engine_url 和 engine_token

    Raises:
        HTTPException: 如果达到最大会话数限制
    """
    try:
        manager = get_session_manager()
        session = manager.create_session(
            tutor_id=request.tutor_id,
            student_id=request.student_id,
            kb_id=request.kb_id
        )

        # 构造 WebSocket URL
        # 检测是否在统一模式下运行（通过检查是否有 /mgmt 前缀的请求）
        # 统一模式: ws://host:port/ws/ws/{session_id}
        # 分开模式: ws://host:port/ws/{session_id}
        import os
        is_unified_mode = os.environ.get("UNIFIED_MODE", "false").lower() == "true"
        
        if is_unified_mode:
            # 统一模式：WebSocket 挂载在 /ws，内部路由是 /ws/{session_id}
            # 所以完整路径是 /ws/ws/{session_id}
            base_url = settings.websocket_url.replace(":9001", f":{settings.management_api_port}")
            engine_url = f"{base_url}/ws/ws/{session.session_id}"
        else:
            # 分开模式：直接使用 websocket_url
            engine_url = f"{settings.websocket_url}/ws/{session.session_id}"

        return CreateSessionResponse(
            session_id=session.session_id,
            engine_url=engine_url,
            engine_token=session.engine_token,
            status=session.status
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )


@app.get("/v1/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """
    查询会话状态

    Args:
        session_id: 会话 ID

    Returns:
        SessionStatusResponse: 会话状态信息

    Raises:
        HTTPException: 如果会话不存在
    """
    manager = get_session_manager()
    session = manager.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )

    return SessionStatusResponse(
        session_id=session.session_id,
        tutor_id=session.tutor_id,
        student_id=session.student_id,
        kb_id=session.kb_id,
        status=session.status,
        created_at=session.to_dict()["created_at"],
        last_activity=session.to_dict()["last_activity"]
    )


@app.delete("/v1/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str):
    """
    结束会话

    Args:
        session_id: 会话 ID

    Raises:
        HTTPException: 如果会话不存在
    """
    manager = get_session_manager()
    success = manager.delete_session(session_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )

    return None


@app.get("/v1/sessions")
async def list_sessions():
    """
    列出所有活跃会话（调试用）

    Returns:
        dict: 所有会话信息
    """
    manager = get_session_manager()
    sessions = manager.get_all_sessions()

    return {
        "total": len(sessions),
        "sessions": [session.to_dict() for session in sessions.values()]
    }


def main():
    """启动管理 API 服务"""
    uvicorn.run(
        app,
        host=settings.management_api_host,
        port=settings.management_api_port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
