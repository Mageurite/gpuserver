# 前端连接指南 - GPU Server 与前端对接

## 📋 架构总览

```
前端 (React, Port 3000)
    ↓ HTTP REST API
Web Server 后端 (FastAPI, Port 8000)
    ↓ HTTP + WebSocket
GPU Server (FastAPI, Port 9000)
    - 管理 API: HTTP
    - 实时对话: WebSocket
```

## 🔗 完整连接流程

### 步骤 1: 用户登录（前端 → Web Server）

```javascript
// 前端代码示例
// 位置: virtual_tutor/app_frontend/src/services/authService.js

const login = async (email, password) => {
    const response = await fetch('http://localhost:8000/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });

    const data = await response.json();
    // 保存 JWT token
    localStorage.setItem('token', data.access_token);
    return data;
};
```

### 步骤 2: 创建会话（前端 → Web Server → GPU Server）

```javascript
// 前端创建会话
// 位置: virtual_tutor/app_frontend/src/services/sessionService.js

const createSession = async (tutorId) => {
    const token = localStorage.getItem('token');

    // 调用 Web Server API
    const response = await fetch('http://localhost:8000/api/student/sessions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ tutor_id: tutorId })
    });

    const session = await response.json();

    // 返回的数据包含：
    // {
    //     "session_id": "uuid",
    //     "engine_url": "ws://localhost:9000/ws/ws/{session_id}",
    //     "engine_token": "token-string",
    //     "status": "active"
    // }

    return session;
};
```

**后端流程（Web Server）：**

```python
# Web Server 代码
# 位置: virtual_tutor/app_backend/app/api/student_sessions.py

@router.post("/sessions")
async def create_session(
    tutor_id: int,
    current_user: User = Depends(get_current_user)
):
    # 1. 验证用户权限
    # 2. 调用 GPU Server 创建会话
    response = await http_client.post(
        f"{settings.ENGINE_URL}/v1/sessions",
        json={
            "tutor_id": tutor_id,
            "student_id": current_user.id,
            "kb_id": tutor.kb_id
        }
    )

    # 3. 保存会话到数据库
    session = Session(
        student_id=current_user.id,
        tutor_id=tutor_id,
        engine_session_id=response["session_id"],
        engine_url=response["engine_url"],
        status="active"
    )
    db.add(session)
    db.commit()

    # 4. 返回会话信息给前端
    return {
        "session_id": session.id,
        "engine_url": response["engine_url"],
        "engine_token": response["engine_token"],
        "status": "active"
    }
```

### 步骤 3: 建立 WebSocket 连接（前端 → GPU Server）

```javascript
// 前端 WebSocket 连接
// 位置: virtual_tutor/app_frontend/src/services/chatService.js

class ChatService {
    constructor() {
        this.ws = null;
        this.sessionId = null;
        this.token = null;
    }

    // 连接到 GPU Server WebSocket
    connect(engineUrl, engineToken) {
        // engineUrl 格式: ws://localhost:9000/ws/ws/{session_id}
        const wsUrl = `${engineUrl}?token=${engineToken}`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket 连接成功');
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket 错误:', error);
        };

        this.ws.onclose = () => {
            console.log('WebSocket 连接关闭');
        };
    }

    // 发送文本消息
    sendText(text) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'text',
                content: text
            }));
        }
    }

    // 发送音频消息
    sendAudio(audioBase64) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'audio',
                data: audioBase64
            }));
        }
    }

    // 处理接收到的消息
    handleMessage(message) {
        switch (message.type) {
            case 'text':
                // 显示 AI 的文本回复
                this.onTextReceived(message.content);
                break;
            case 'audio':
                // 播放 AI 的语音回复
                this.onAudioReceived(message.data);
                break;
            case 'transcription':
                // 显示语音转文本结果
                this.onTranscriptionReceived(message.content);
                break;
            case 'error':
                // 处理错误
                this.onError(message.content);
                break;
        }
    }

    // 断开连接
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

export default new ChatService();
```

### 步骤 4: 使用 WebSocket（React 组件示例）

```javascript
// React 组件中使用
// 位置: virtual_tutor/app_frontend/src/components/ChatPage.js

import React, { useState, useEffect } from 'react';
import chatService from '../services/chatService';
import sessionService from '../services/sessionService';

function ChatPage({ tutorId }) {
    const [messages, setMessages] = useState([]);
    const [inputText, setInputText] = useState('');
    const [connected, setConnected] = useState(false);

    useEffect(() => {
        // 组件加载时创建会话并连接
        initializeChat();

        // 组件卸载时断开连接
        return () => {
            chatService.disconnect();
        };
    }, [tutorId]);

    const initializeChat = async () => {
        try {
            // 1. 创建会话
            const session = await sessionService.createSession(tutorId);

            // 2. 连接 WebSocket
            chatService.connect(session.engine_url, session.engine_token);

            // 3. 设置消息接收回调
            chatService.onTextReceived = (text) => {
                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: text,
                    timestamp: new Date()
                }]);
            };

            setConnected(true);
        } catch (error) {
            console.error('初始化聊天失败:', error);
        }
    };

    const handleSendMessage = () => {
        if (inputText.trim() && connected) {
            // 添加用户消息到界面
            setMessages(prev => [...prev, {
                role: 'user',
                content: inputText,
                timestamp: new Date()
            }]);

            // 发送到 GPU Server
            chatService.sendText(inputText);

            // 清空输入框
            setInputText('');
        }
    };

    return (
        <div className="chat-container">
            <div className="messages">
                {messages.map((msg, idx) => (
                    <div key={idx} className={`message ${msg.role}`}>
                        <div className="content">{msg.content}</div>
                        <div className="timestamp">
                            {msg.timestamp.toLocaleTimeString()}
                        </div>
                    </div>
                ))}
            </div>

            <div className="input-area">
                <input
                    type="text"
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                    placeholder="输入消息..."
                    disabled={!connected}
                />
                <button
                    onClick={handleSendMessage}
                    disabled={!connected}
                >
                    发送
                </button>
            </div>

            <div className="status">
                {connected ? '已连接' : '连接中...'}
            </div>
        </div>
    );
}

export default ChatPage;
```

## 🔧 配置清单

### 1. GPU Server 配置

```bash
# /workspace/gpuserver/.env

MANAGEMENT_API_HOST=0.0.0.0
MANAGEMENT_API_PORT=9000
WEBSOCKET_URL=ws://localhost:9000
MAX_SESSIONS=10
SESSION_TIMEOUT_SECONDS=3600
ENABLE_LLM=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
DEFAULT_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16
```

### 2. Web Server 配置

```bash
# /workspace/virtual_tutor/app_backend/.env

# GPU Server 地址（重要！）
ENGINE_URL=http://localhost:9000

# 数据库配置
DATABASE_URL=sqlite:///./virtual_tutor.db

# JWT 配置
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### 3. 前端配置

```bash
# /workspace/virtual_tutor/app_frontend/.env

# Web Server API 地址
REACT_APP_API_BASE_URL=http://localhost:8000/api
REACT_APP_BACKEND_URL=http://localhost:8000
```

## 🚀 启动顺序

### 1. 启动 GPU Server

```bash
cd /workspace/gpuserver
./start.sh

# 验证
curl http://localhost:9000/health
```

### 2. 启动 Web Server

```bash
cd /workspace/virtual_tutor/app_backend

# 确保配置了 ENGINE_URL
cat .env | grep ENGINE_URL
# 应该显示: ENGINE_URL=http://localhost:9000

# 启动
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 验证
curl http://localhost:8000/health
```

### 3. 启动前端

```bash
cd /workspace/virtual_tutor/app_frontend

# 确保配置了 API 地址
cat .env | grep REACT_APP_API_BASE_URL
# 应该显示: REACT_APP_API_BASE_URL=http://localhost:8000/api

# 安装依赖（首次）
npm install

# 启动
npm start

# 前端将在 http://localhost:3000 运行
```

## ✅ 验证连接

### 方法 1: 使用测试脚本

```bash
cd /workspace/gpuserver
./test_webserver_connection.sh
```

### 方法 2: 手动测试

```bash
# 1. 测试 GPU Server
curl http://localhost:9000/health

# 2. 测试 Web Server
curl http://localhost:8000/health

# 3. 测试创建会话（需要先获取 JWT token）
# 3.1 登录获取 token
TOKEN=$(curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}' \
  | jq -r '.access_token')

# 3.2 创建会话
curl -X POST http://localhost:8000/api/student/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1}'
```

### 方法 3: 浏览器测试

1. 打开浏览器访问 http://localhost:3000
2. 登录（如果需要）
3. 选择一个导师开始对话
4. 打开浏览器开发者工具（F12）
5. 切换到 Network 标签
6. 筛选 WS（WebSocket）
7. 应该能看到 WebSocket 连接到 `ws://localhost:9000/ws/ws/{session_id}`

## 📊 数据流图

```
用户在前端输入消息
    ↓
前端: WebSocket.send({ type: 'text', content: '你好' })
    ↓
GPU Server: WebSocket 接收消息
    ↓
GPU Server: AI Engine 处理（LLM 生成回复）
    ↓
GPU Server: WebSocket.send({ type: 'text', content: '你好！我能帮你什么？', role: 'assistant' })
    ↓
前端: WebSocket.onmessage 接收消息
    ↓
前端: 更新 UI 显示 AI 回复
```

## 🐛 常见问题

### Q1: WebSocket 连接失败 "连接被拒绝"

**原因**: GPU Server 未启动或端口不对

**解决**:
```bash
# 检查 GPU Server 状态
cd /workspace/gpuserver
./status.sh

# 如果未运行，启动它
./start.sh
```

### Q2: 前端无法连接到 Web Server

**原因**: CORS 配置或 Web Server 未启动

**解决**:
```bash
# 检查 Web Server
curl http://localhost:8000/health

# 检查 CORS 配置
# 确保 Web Server 的 main.py 中有：
# app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], ...)
```

### Q3: 会话创建成功但 WebSocket 无法连接

**原因**: engine_url 或 engine_token 不正确

**解决**:
```bash
# 1. 测试创建会话
curl -X POST http://localhost:9000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 123}'

# 2. 记录返回的 engine_url 和 engine_token
# 3. 在前端确保完整的 URL 和 token 被使用
```

### Q4: 消息发送后没有回复

**原因**: LLM 未启用或 Ollama 未运行

**解决**:
```bash
# 1. 检查 GPU Server 配置
cat /workspace/gpuserver/.env | grep ENABLE_LLM
# 应该是: ENABLE_LLM=true

# 2. 检查 Ollama
curl http://127.0.0.1:11434/api/tags

# 3. 查看 GPU Server 日志
tail -f /workspace/gpuserver/logs/server.log
```

## 📚 相关文档

- [GPU Server README](README.md)
- [脚本使用指南](SCRIPTS_GUIDE.md)
- [快速参考](QUICK_REFERENCE.md)
- [连接测试](test_webserver_connection.sh)

---

**最后更新**: 2025-12-23
