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

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
