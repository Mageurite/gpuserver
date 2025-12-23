import uuid
import time
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import secrets


@dataclass
class Session:
    """会话数据类"""
    session_id: str
    tutor_id: int
    student_id: int
    kb_id: Optional[str]
    engine_token: str
    status: str = "active"  # active, idle, closed
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "tutor_id": self.tutor_id,
            "student_id": self.student_id,
            "kb_id": self.kb_id,
            "engine_token": self.engine_token,
            "status": self.status,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "last_activity": datetime.fromtimestamp(self.last_activity).isoformat(),
        }


class SessionManager:
    """
    会话管理器

    负责管理 AI 推理引擎的会话生命周期：
    - 创建会话并生成 engine_token
    - 查询会话状态
    - 结束会话
    - 验证 engine_token
    """

    def __init__(self, max_sessions: int = 10, session_timeout: int = 3600):
        self.sessions: Dict[str, Session] = {}
        self.tokens: Dict[str, str] = {}  # token -> session_id 映射
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout

    def create_session(
        self,
        tutor_id: int,
        student_id: int,
        kb_id: Optional[str] = None
    ) -> Session:
        """
        创建新会话

        Args:
            tutor_id: 导师 ID
            student_id: 学生 ID
            kb_id: 知识库 ID（可选）

        Returns:
            Session: 新创建的会话对象

        Raises:
            RuntimeError: 如果达到最大会话数限制
        """
        # 清理过期会话
        self._cleanup_expired_sessions()

        # 检查会话数限制
        if len(self.sessions) >= self.max_sessions:
            raise RuntimeError(f"Maximum sessions ({self.max_sessions}) reached")

        # 生成唯一 ID 和 token
        session_id = str(uuid.uuid4())
        engine_token = secrets.token_urlsafe(32)

        # 创建会话对象
        session = Session(
            session_id=session_id,
            tutor_id=tutor_id,
            student_id=student_id,
            kb_id=kb_id,
            engine_token=engine_token,
            status="active"
        )

        # 保存会话
        self.sessions[session_id] = session
        self.tokens[engine_token] = session_id

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取会话信息

        Args:
            session_id: 会话 ID

        Returns:
            Session: 会话对象，如果不存在返回 None
        """
        return self.sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话 ID

        Returns:
            bool: 删除成功返回 True，会话不存在返回 False
        """
        session = self.sessions.get(session_id)
        if not session:
            return False

        # 删除会话和 token 映射
        self.sessions.pop(session_id, None)
        self.tokens.pop(session.engine_token, None)

        return True

    def verify_token(self, token: str) -> Optional[str]:
        """
        验证 engine_token 并返回对应的 session_id

        Args:
            token: engine_token

        Returns:
            str: 会话 ID，如果 token 无效返回 None
        """
        return self.tokens.get(token)

    def update_activity(self, session_id: str):
        """
        更新会话的最后活动时间

        Args:
            session_id: 会话 ID
        """
        session = self.sessions.get(session_id)
        if session:
            session.last_activity = time.time()

    def _cleanup_expired_sessions(self):
        """清理过期会话"""
        current_time = time.time()
        expired_sessions = [
            session_id
            for session_id, session in self.sessions.items()
            if current_time - session.last_activity > self.session_timeout
        ]

        for session_id in expired_sessions:
            self.delete_session(session_id)

    def get_all_sessions(self) -> Dict[str, Session]:
        """获取所有会话"""
        self._cleanup_expired_sessions()
        return self.sessions.copy()


# 全局会话管理器实例
session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取全局会话管理器实例"""
    global session_manager
    if session_manager is None:
        from config import settings
        session_manager = SessionManager(
            max_sessions=settings.max_sessions,
            session_timeout=settings.session_timeout_seconds
        )
    return session_manager
