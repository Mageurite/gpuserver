# Web Server 集成 GPU Server 指南

## 📋 目标

将 Web Server (`/workspace/virtual_tutor/app_backend`) 与 GPU Server (`/workspace/gpuserver`) 集成，实现完整的 AI 对话功能。

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────┐
│         Web Server (Port 8000)          │
│  ┌────────────────────────────────────┐ │
│  │ FastAPI Backend                    │ │
│  │ - 用户认证 (JWT)                   │ │
│  │ - 数据持久化 (SQLite)              │ │
│  │ - 会话管理                         │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
         │ HTTP API
         ▼
┌─────────────────────────────────────────┐
│       GPU Server (Port 9000)            │
│  ┌────────────────────────────────────┐ │
│  │ AI 推理引擎                        │ │
│  │ - LLM (Ollama)                     │ │
│  │ - ASR/TTS                          │ │
│  │ - MuseTalk (视频生成)              │ │
│  │ - WebSocket 实时对话               │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
         │ WebSocket
         ▼
┌─────────────────────────────────────────┐
│      React Frontend (Port 3000)         │
└─────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 步骤 1: 配置 Web Server

编辑 `/workspace/virtual_tutor/app_backend/.env`:

```bash
# 添加 GPU Server 配置
ENGINE_URL=http://localhost:9000
ENGINE_ENABLED=true
```

### 步骤 2: 添加配置类

编辑 `/workspace/virtual_tutor/app_backend/app/core/config.py`:

```python
class Settings:
    PROJECT_NAME: str = "Virtual Tutor System"

    # ... 现有配置 ...

    # GPU Server 配置
    ENGINE_URL: str = os.getenv("ENGINE_URL", "http://localhost:9000")
    ENGINE_ENABLED: bool = os.getenv("ENGINE_ENABLED", "true").lower() == "true"
```

### 步骤 3: 创建 GPU Server 客户端

创建文件 `/workspace/virtual_tutor/app_backend/app/services/gpu_client.py`:

```python
"""GPU Server 客户端"""
import httpx
from typing import Optional, Dict, Any
from app.core.config import settings


class GPUServerClient:
    """GPU Server HTTP 客户端"""

    def __init__(self):
        self.base_url = settings.ENGINE_URL
        self.timeout = 30.0

    async def create_session(
        self,
        tutor_id: int,
        student_id: int,
        kb_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        创建 AI 会话

        Args:
            tutor_id: 导师ID
            student_id: 学生ID
            kb_id: 知识库ID（可选）

        Returns:
            {
                "session_id": "uuid",
                "engine_url": "ws://...",
                "engine_token": "token",
                "status": "active"
            }
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/sessions",
                json={
                    "tutor_id": tutor_id,
                    "student_id": student_id,
                    "kb_id": kb_id
                }
            )
            response.raise_for_status()
            return response.json()

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """获取会话状态"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/v1/sessions/{session_id}"
            )
            response.raise_for_status()
            return response.json()

    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.delete(
                f"{self.base_url}/v1/sessions/{session_id}"
            )
            return response.status_code == 204

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()


# 全局实例
gpu_client = GPUServerClient()
```

### 步骤 4: 创建学生会话路由

创建文件 `/workspace/virtual_tutor/app_backend/app/api/routes_sessions.py`:

```python
"""学生会话管理路由"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_current_user, get_db
from app.models.tutor import User
from app.services.gpu_client import gpu_client
from app.core.config import settings
from pydantic import BaseModel


router = APIRouter(prefix="/api/student", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    tutor_id: int
    kb_id: Optional[str] = None


class SessionResponse(BaseModel):
    """会话响应"""
    session_id: str
    engine_url: str
    engine_token: str
    status: str


@router.post("/sessions", response_model=SessionResponse)
async def create_student_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    创建学生会话

    - 验证用户身份
    - 调用 GPU Server 创建会话
    - 返回 WebSocket 连接信息
    """
    if not settings.ENGINE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GPU Server is not enabled"
        )

    try:
        # 调用 GPU Server 创建会话
        session_data = await gpu_client.create_session(
            tutor_id=request.tutor_id,
            student_id=current_user.id,
            kb_id=request.kb_id
        )

        return SessionResponse(**session_data)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


@router.get("/sessions/{session_id}")
async def get_session_status(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取会话状态"""
    try:
        session_data = await gpu_client.get_session(session_id)
        return session_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {str(e)}"
        )


@router.delete("/sessions/{session_id}")
async def end_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """结束会话"""
    try:
        success = await gpu_client.delete_session(session_id)
        if success:
            return {"message": "Session ended successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to end session"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error ending session: {str(e)}"
        )


@router.get("/gpu/health")
async def check_gpu_health():
    """检查 GPU Server 健康状态"""
    try:
        health = await gpu_client.health_check()
        return {
            "gpu_server": health,
            "enabled": settings.ENGINE_ENABLED
        }
    except Exception as e:
        return {
            "gpu_server": {"status": "unhealthy", "error": str(e)},
            "enabled": settings.ENGINE_ENABLED
        }
```

### 步骤 5: 注册路由

编辑 `/workspace/virtual_tutor/app_backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db import Base, engine
from app import models  # noqa: F401
from app.api.routes_auth import router as auth_router
from app.api.routes_tutors import router as tutors_router
from app.api.routes_sessions import router as sessions_router  # 新增


def create_app() -> FastAPI:
    Base.metadata.create_all(bind=engine)

    app = FastAPI(title=settings.PROJECT_NAME)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    # 注册路由
    app.include_router(auth_router)
    app.include_router(tutors_router)
    app.include_router(sessions_router)  # 新增

    return app


app = create_app()
```

### 步骤 6: 安装依赖

```bash
cd /workspace/virtual_tutor/app_backend
pip install httpx
```

### 步骤 7: 启动服务

```bash
# 终端 1: 启动 GPU Server
cd /workspace/gpuserver
./start_mt.sh

# 终端 2: 启动 Web Server
cd /workspace/virtual_tutor/app_backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🧪 测试集成

### 1. 测试 GPU Server 健康状态

```bash
curl http://localhost:8000/api/student/gpu/health
```

**预期响应**:
```json
{
  "gpu_server": {
    "status": "healthy",
    "service": "GPU Server"
  },
  "enabled": true
}
```

### 2. 测试创建会话

首先登录获取 JWT token:

```bash
# 登录
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "admin123"
  }'
```

使用返回的 token 创建会话:

```bash
curl -X POST http://localhost:8000/api/student/sessions \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tutor_id": 1,
    "kb_id": "optional"
  }'
```

**预期响应**:
```json
{
  "session_id": "uuid-here",
  "engine_url": "ws://localhost:9000/ws/ws/uuid-here",
  "engine_token": "token-here",
  "status": "active"
}
```

---

## 🌐 前端集成

### React 示例代码

创建文件 `frontend/src/services/aiService.js`:

```javascript
/**
 * AI 服务 - 与 GPU Server 通信
 */

const API_BASE = 'http://localhost:8000';

/**
 * 创建 AI 会话
 */
export async function createAISession(tutorId, kbId = null) {
  const token = localStorage.getItem('jwt_token');

  const response = await fetch(`${API_BASE}/api/student/sessions`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      tutor_id: tutorId,
      kb_id: kbId
    })
  });

  if (!response.ok) {
    throw new Error('Failed to create session');
  }

  return await response.json();
}

/**
 * 连接 WebSocket
 */
export function connectWebSocket(engineUrl, engineToken, callbacks) {
  const ws = new WebSocket(`${engineUrl}?token=${engineToken}`);

  ws.onopen = () => {
    console.log('WebSocket connected');
    if (callbacks.onOpen) callbacks.onOpen();
  };

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    console.log('Received:', message);

    if (callbacks.onMessage) {
      callbacks.onMessage(message);
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    if (callbacks.onError) callbacks.onError(error);
  };

  ws.onclose = () => {
    console.log('WebSocket closed');
    if (callbacks.onClose) callbacks.onClose();
  };

  return ws;
}

/**
 * 发送文本消息
 */
export function sendTextMessage(ws, content, avatarId = null) {
  const message = {
    type: 'text',
    content: content
  };

  if (avatarId) {
    message.avatar_id = avatarId;
  }

  ws.send(JSON.stringify(message));
}

/**
 * 发送音频消息
 */
export function sendAudioMessage(ws, audioBase64) {
  const message = {
    type: 'audio',
    data: audioBase64
  };

  ws.send(JSON.stringify(message));
}
```

### React 组件示例

创建文件 `frontend/src/components/AIChat.jsx`:

```javascript
import React, { useState, useEffect, useRef } from 'react';
import { createAISession, connectWebSocket, sendTextMessage } from '../services/aiService';

export default function AIChat({ tutorId, avatarId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [videoUrl, setVideoUrl] = useState(null);
  const wsRef = useRef(null);

  useEffect(() => {
    // 初始化连接
    initConnection();

    return () => {
      // 清理连接
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [tutorId]);

  async function initConnection() {
    try {
      // 1. 创建会话
      const session = await createAISession(tutorId);
      console.log('Session created:', session);

      // 2. 连接 WebSocket
      wsRef.current = connectWebSocket(
        session.engine_url,
        session.engine_token,
        {
          onOpen: () => {
            setConnected(true);
            console.log('Connected to AI');
          },
          onMessage: handleMessage,
          onError: (error) => {
            console.error('Connection error:', error);
            setConnected(false);
          },
          onClose: () => {
            setConnected(false);
            console.log('Disconnected from AI');
          }
        }
      );
    } catch (error) {
      console.error('Failed to initialize:', error);
      alert('无法连接到 AI 服务');
    }
  }

  function handleMessage(message) {
    if (message.type === 'text') {
      // 文本响应
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: message.content,
        timestamp: message.timestamp
      }]);
    } else if (message.type === 'video') {
      // 视频响应
      const videoBlob = base64ToBlob(message.video, 'video/mp4');
      const videoUrl = URL.createObjectURL(videoBlob);
      setVideoUrl(videoUrl);

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: message.content,
        video: videoUrl,
        timestamp: message.timestamp
      }]);
    } else if (message.type === 'transcription') {
      // 语音转文本
      setMessages(prev => [...prev, {
        role: 'user',
        content: message.content,
        timestamp: message.timestamp
      }]);
    }
  }

  function handleSend() {
    if (!input.trim() || !connected) return;

    // 添加用户消息
    setMessages(prev => [...prev, {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString()
    }]);

    // 发送到 AI
    sendTextMessage(wsRef.current, input, avatarId);

    // 清空输入
    setInput('');
  }

  function base64ToBlob(base64, mimeType) {
    const byteCharacters = atob(base64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    return new Blob([byteArray], { type: mimeType });
  }

  return (
    <div className="ai-chat">
      <div className="status">
        {connected ? '🟢 已连接' : '🔴 未连接'}
      </div>

      {/* 视频显示 */}
      {videoUrl && (
        <div className="video-container">
          <video src={videoUrl} autoPlay controls />
        </div>
      )}

      {/* 消息列表 */}
      <div className="messages">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <div className="content">{msg.content}</div>
            {msg.video && (
              <video src={msg.video} controls width="300" />
            )}
          </div>
        ))}
      </div>

      {/* 输入框 */}
      <div className="input-area">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSend()}
          placeholder="输入消息..."
          disabled={!connected}
        />
        <button onClick={handleSend} disabled={!connected}>
          发送
        </button>
      </div>
    </div>
  );
}
```

---

## 📊 API 参考

### Web Server API

#### 创建会话
```
POST /api/student/sessions
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "tutor_id": 1,
  "kb_id": "optional"
}

Response 200:
{
  "session_id": "uuid",
  "engine_url": "ws://localhost:9000/ws/ws/uuid",
  "engine_token": "token",
  "status": "active"
}
```

#### 获取会话状态
```
GET /api/student/sessions/{session_id}
Authorization: Bearer {jwt_token}

Response 200:
{
  "session_id": "uuid",
  "tutor_id": 1,
  "student_id": 123,
  "status": "active",
  "created_at": "2025-12-28T...",
  "last_activity": "2025-12-28T..."
}
```

#### 结束会话
```
DELETE /api/student/sessions/{session_id}
Authorization: Bearer {jwt_token}

Response 200:
{
  "message": "Session ended successfully"
}
```

#### GPU Server 健康检查
```
GET /api/student/gpu/health

Response 200:
{
  "gpu_server": {
    "status": "healthy",
    "service": "GPU Server"
  },
  "enabled": true
}
```

### WebSocket 消息格式

#### 客户端发送

**文本消息**:
```json
{
  "type": "text",
  "content": "你好",
  "avatar_id": "avatar_tutor_13"
}
```

**音频消息**:
```json
{
  "type": "audio",
  "data": "base64_encoded_audio"
}
```

#### 服务器响应

**文本响应**:
```json
{
  "type": "text",
  "content": "你好！有什么可以帮助你的吗？",
  "role": "assistant",
  "timestamp": "2025-12-28T..."
}
```

**视频响应**:
```json
{
  "type": "video",
  "video": "base64_encoded_video",
  "audio": "base64_encoded_audio",
  "content": "你好！有什么可以帮助你的吗？",
  "role": "assistant",
  "timestamp": "2025-12-28T..."
}
```

**转录结果**:
```json
{
  "type": "transcription",
  "content": "转录的文本",
  "role": "user",
  "timestamp": "2025-12-28T..."
}
```

---

## 🔧 故障排除

### 问题 1: 无法连接到 GPU Server

**症状**: `Failed to create session: Connection refused`

**解决方案**:
1. 确认 GPU Server 正在运行:
   ```bash
   curl http://localhost:9000/health
   ```

2. 检查 `.env` 配置:
   ```bash
   cat /workspace/virtual_tutor/app_backend/.env | grep ENGINE
   ```

3. 检查防火墙设置

### 问题 2: WebSocket 连接失败

**症状**: 前端无法连接 WebSocket

**解决方案**:
1. 确认 `engine_url` 格式正确: `ws://localhost:9000/ws/ws/{session_id}`
2. 确认 `engine_token` 有效
3. 检查浏览器控制台错误信息

### 问题 3: 视频不显示

**症状**: 收到视频消息但无法播放

**解决方案**:
1. 确认 `avatar_id` 参数正确
2. 检查 GPU Server 日志: `tail -f /workspace/gpuserver/logs/unified_server.log`
3. 确认使用 mt 环境启动 GPU Server

---

## 📚 相关文档

- [GPU Server 集成测试报告](../../gpuserver/INTEGRATION_TEST_REPORT.md)
- [GPU Server 启动指南](../../gpuserver/STARTUP_SCRIPTS_GUIDE.md)
- [端到端管道说明](../../gpuserver/END_TO_END_PIPELINE_SUMMARY.md)
- [项目架构文档](../../claude.md)

---

## ✅ 检查清单

### Web Server 后端
- [ ] 添加 `ENGINE_URL` 配置
- [ ] 创建 `gpu_client.py`
- [ ] 创建 `routes_sessions.py`
- [ ] 注册新路由
- [ ] 安装 `httpx` 依赖
- [ ] 测试健康检查接口
- [ ] 测试创建会话接口

### 前端
- [ ] 创建 `aiService.js`
- [ ] 创建 `AIChat` 组件
- [ ] 实现 WebSocket 连接
- [ ] 实现消息发送/接收
- [ ] 实现视频显示
- [ ] 端到端测试

---

**最后更新**: 2025-12-28
**状态**: 就绪，可以开始集成
