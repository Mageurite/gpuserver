"""
TTS (Text-to-Speech) Module

This module provides TTS functionality for the GPU Server.
Supports both real TTS models and Mock mode for testing.
"""

from .tts_engine import TTSEngine, get_tts_engine

__all__ = ["TTSEngine", "get_tts_engine"]
