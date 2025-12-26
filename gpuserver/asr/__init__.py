"""
ASR (Automatic Speech Recognition) Module

This module provides ASR functionality for the GPU Server.
Supports both real Whisper models and Mock mode for testing.
"""

from .asr_engine import ASREngine, get_asr_engine

__all__ = ["ASREngine", "get_asr_engine"]
