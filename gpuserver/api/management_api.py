from fastapi import FastAPI, HTTPException, status, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import os
import shutil
import tempfile

from config import settings
from session_manager import get_session_manager
from musetalk import get_avatar_manager


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

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应该配置具体域名
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有请求头
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
@app.post("/mgmt/v1/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
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


# ====================================
# Avatar Management API
# ====================================

class CreateAvatarRequest(BaseModel):
    """创建 Avatar 请求（从视频路径）"""
    avatar_id: str
    video_path: str
    apply_blur: bool = False
    tutor_id: Optional[int] = None


class AvatarResponse(BaseModel):
    """Avatar 响应"""
    status: str
    avatar_id: str
    avatar_path: Optional[str] = None
    message: str
    mock: Optional[bool] = None


@app.post("/v1/avatars", response_model=AvatarResponse, status_code=status.HTTP_201_CREATED)
@app.post("/mgmt/v1/avatars", response_model=AvatarResponse, status_code=status.HTTP_201_CREATED)
async def create_avatar_from_path(request: CreateAvatarRequest):
    """
    从视频路径创建 Avatar（教师端使用）

    Args:
        request: 创建 Avatar 请求

    Returns:
        AvatarResponse: Avatar 创建结果
    """
    try:
        avatar_manager = get_avatar_manager(
            enable_real=settings.enable_avatar,
            avatars_dir=settings.avatars_dir,
            musetalk_base=settings.musetalk_base,
            conda_env=settings.musetalk_conda_env,
            ffmpeg_path=settings.ffmpeg_path
        )

        # 验证视频文件存在
        if not os.path.exists(request.video_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video file not found: {request.video_path}"
            )

        # 创建 Avatar
        result = await avatar_manager.create_avatar(
            avatar_id=request.avatar_id,
            video_path=request.video_path,
            apply_blur=request.apply_blur,
            tutor_id=request.tutor_id
        )

        return AvatarResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create avatar: {str(e)}"
        )


@app.post("/v1/avatars/upload", response_model=AvatarResponse, status_code=status.HTTP_201_CREATED)
@app.post("/mgmt/v1/avatars/upload", response_model=AvatarResponse, status_code=status.HTTP_201_CREATED)
async def create_avatar_from_upload(
    avatar_id: str = Form(...),
    apply_blur: bool = Form(False),
    tutor_id: Optional[int] = Form(None),
    video_file: UploadFile = File(...)
):
    """
    从上传的视频文件创建 Avatar（教师端使用）

    Args:
        avatar_id: Avatar 唯一标识符
        apply_blur: 是否应用背景模糊
        tutor_id: 关联的 Tutor ID
        video_file: 上传的视频文件

    Returns:
        AvatarResponse: Avatar 创建结果
    """
    temp_video_path = None

    try:
        avatar_manager = get_avatar_manager(
            enable_real=settings.enable_avatar,
            avatars_dir=settings.avatars_dir,
            musetalk_base=settings.musetalk_base,
            conda_env=settings.musetalk_conda_env,
            ffmpeg_path=settings.ffmpeg_path
        )

        # 创建临时目录保存上传的视频
        temp_dir = tempfile.mkdtemp(prefix="avatar_upload_")
        temp_video_path = os.path.join(temp_dir, video_file.filename)

        # 保存上传的文件
        with open(temp_video_path, "wb") as f:
            shutil.copyfileobj(video_file.file, f)

        # 创建 Avatar
        result = await avatar_manager.create_avatar(
            avatar_id=avatar_id,
            video_path=temp_video_path,
            apply_blur=apply_blur,
            tutor_id=tutor_id
        )

        return AvatarResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create avatar: {str(e)}"
        )
    finally:
        # 清理临时文件
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
                os.rmdir(os.path.dirname(temp_video_path))
            except:
                pass


@app.get("/v1/avatars/{avatar_id}")
async def get_avatar(avatar_id: str):
    """
    获取 Avatar 信息

    Args:
        avatar_id: Avatar ID

    Returns:
        dict: Avatar 信息

    Raises:
        HTTPException: 如果 Avatar 不存在
    """
    avatar_manager = get_avatar_manager(
        enable_real=settings.enable_avatar,
        avatars_dir=settings.avatars_dir
    )

    avatar_info = await avatar_manager.get_avatar(avatar_id)

    if not avatar_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Avatar {avatar_id} not found"
        )

    return avatar_info


@app.delete("/v1/avatars/{avatar_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_avatar(avatar_id: str):
    """
    删除 Avatar

    Args:
        avatar_id: Avatar ID

    Raises:
        HTTPException: 如果 Avatar 不存在
    """
    avatar_manager = get_avatar_manager(
        enable_real=settings.enable_avatar,
        avatars_dir=settings.avatars_dir
    )

    success = await avatar_manager.delete_avatar(avatar_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Avatar {avatar_id} not found"
        )

    return None


@app.get("/v1/avatars")
async def list_avatars():
    """
    列出所有 Avatar

    Returns:
        dict: Avatar 列表
    """
    avatar_manager = get_avatar_manager(
        enable_real=settings.enable_avatar,
        avatars_dir=settings.avatars_dir
    )

    avatars = await avatar_manager.list_avatars()

    return {
        "total": len(avatars),
        "avatars": avatars
    }


@app.get("/v1/webrtc/config")
@app.get("/mgmt/v1/webrtc/config")
@app.get("/api/webrtc/config")
@app.get("/config")  # 兼容性路由，供前端直接访问
async def get_webrtc_config():
    """
    获取 WebRTC 配置信息
    
    前端需要这些配置来正确建立WebRTC连接
    
    Returns:
        dict: WebRTC 配置，包括 ICE 服务器等
    """
    # 使用通过 FRP 映射的 TURN 服务器
    # 前端通过 Web Server (51.161.130.234:10110) 访问 GPU Server 的 TURN 服务器
    return {
        "iceServers": [
            {
                "urls": ["stun:stun.l.google.com:19302"]
            },
            {
                "urls": ["turn:51.161.209.200:10110"],  # GPU服务器的公网IP
                "username": settings.webrtc_turn_username,
                "credential": settings.webrtc_turn_password
            }
        ],
        "iceTransportPolicy": "relay",  # 强制使用 TURN relay，确保流量通过 10110-10115 端口
        "publicIp": settings.webrtc_public_ip,
        "portRange": {
            "min": settings.webrtc_port_min,
            "max": settings.webrtc_port_max
        },
        "sdpSemantics": "unified-plan"
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

