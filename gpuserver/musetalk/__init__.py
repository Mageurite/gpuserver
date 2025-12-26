"""
MuseTalk Module for GPU Server

This module provides Avatar creation and management functionality.
It integrates with the MuseTalk system for lip-sync video generation.

Architecture:
- Avatar Manager: Creates and manages digital avatars
- Integration with MuseTalk: Calls MuseTalk scripts for avatar creation
- Video Processing: Handles video upload, processing, and blur

Reference:
- Full implementation: /workspace/try/lip-sync/
- MuseTalk base: /workspace/MuseTalk/
"""

from .avatar_manager import AvatarManager, get_avatar_manager

__all__ = ["AvatarManager", "get_avatar_manager"]
