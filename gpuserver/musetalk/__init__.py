"""
MuseTalk Module for GPU Server

This module provides Avatar creation and management functionality.
It integrates with the MuseTalk system for lip-sync video generation.

Architecture:
- Avatar Manager: Creates and manages digital avatars
- Integration with MuseTalk: Calls MuseTalk scripts for avatar creation
- Video Processing: Handles video upload, processing, and blur
- Streaming Engine: Real-time TTS + Lip-Sync with low latency

Reference:
- Full implementation: /workspace/try/lip-sync/
- MuseTalk base: /workspace/MuseTalk/
"""

from .avatar_manager import AvatarManager, get_avatar_manager

# 流式引擎（低延迟TTS+Lip-Sync）
from .streaming_engine import (
    StreamingLipSyncEngine,
    StreamingTTSWorker,
    StreamingASR,
    get_streaming_engine,
    warmup_streaming_engine
)

def get_video_engine(
    enable_real: bool = False,
    avatars_dir: str = None,
    musetalk_base: str = None,
    conda_env: str = None,
    ffmpeg_path: str = None
):
    """获取视频生成引擎"""
    return get_avatar_manager(
        enable_real=enable_real,
        avatars_dir=avatars_dir,
        musetalk_base=musetalk_base,
        conda_env=conda_env,
        ffmpeg_path=ffmpeg_path
    )

__all__ = [
    "AvatarManager", 
    "get_avatar_manager", 
    "get_video_engine",
    # 流式引擎
    "StreamingLipSyncEngine",
    "StreamingTTSWorker", 
    "StreamingASR",
    "get_streaming_engine",
    "warmup_streaming_engine"
]
