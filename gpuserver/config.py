import os
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """GPU Server 配置"""

    # 管理 API 配置
    management_api_host: str = "0.0.0.0"
    management_api_port: int = 9000

    # WebSocket 配置
    websocket_host: str = "0.0.0.0"
    websocket_port: int = 9001
    websocket_url: str = "ws://localhost:9001"

    # GPU 配置
    cuda_visible_devices: str = "0"

    # 会话配置
    max_sessions: int = 10
    session_timeout_seconds: int = 3600

    # LLM 配置
    ollama_base_url: str = "http://127.0.0.1:11434"
    default_llm_model: str = "mistral-nemo:12b-instruct-2407-fp16"
    llm_temperature: float = 0.4
    # 是否启用 LLM（如果为 False，则使用 Mock 模式）
    enable_llm: bool = True

    # ASR 配置
    # Whisper 模型: tiny, base, small, medium, large
    asr_model: str = "base"
    # 是否启用 ASR（如果为 False，则使用 Mock 模式）
    enable_asr: bool = True
    # ASR 设备: cuda 或 cpu
    asr_device: str = "cuda"
    # ASR 默认语言: zh (中文), en (英文)
    asr_language: str = "zh"

    # TTS 配置
    # Edge TTS 声音: zh-CN-XiaoxiaoNeural (中文女声), zh-CN-YunxiNeural (中文男声)
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    # 是否启用 TTS（如果为 False，则使用 Mock 模式）
    enable_tts: bool = True

    # RAG 配置
    # 是否启用 RAG（如果为 False，则使用 Mock 模式）
    enable_rag: bool = False
    # RAG 服务 URL（如果使用独立的 RAG 服务）
    rag_url: Optional[str] = None
    # RAG 检索返回的文档数量
    rag_top_k: int = 5

    # MuseTalk / Avatar 配置
    # 是否启用 MuseTalk（如果为 False，则使用 Mock 模式）
    enable_avatar: bool = True  # 启用 Avatar 以支持 TTS 驱动口型
    # Avatar 存储目录
    avatars_dir: str = "/workspace/gpuserver/data/avatars"
    # MuseTalk 基础目录
    musetalk_base: str = "/workspace/MuseTalk"
    # MuseTalk Conda 环境路径
    musetalk_conda_env: Optional[str] = None
    # FFmpeg 路径
    ffmpeg_path: str = "ffmpeg"

    # WebRTC 配置
    # 公网IP地址（用于WebRTC连接）
    webrtc_public_ip: str = "51.161.209.200"
    # WebRTC端口范围起始
    webrtc_port_min: int = 10110
    # WebRTC端口范围结束
    webrtc_port_max: int = 10115
    # STUN服务器URL
    webrtc_stun_server: str = "stun:stun.l.google.com:19302"
    # TURN服务器URL（GPU服务器本地连接）
    webrtc_turn_server: str = "turn:127.0.0.1:10110"
    # TURN服务器用户名
    webrtc_turn_username: str = "vtuser"
    # TURN服务器密码
    webrtc_turn_password: str = "vtpass"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
