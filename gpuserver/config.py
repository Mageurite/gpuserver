import os
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

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
