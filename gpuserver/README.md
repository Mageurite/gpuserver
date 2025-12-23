# GPU Server - AI 推理引擎

这是 Virtual Tutor System 的 GPU Server 实现，负责处理 AI 推理和实时对话。

## 📋 概述

GPU Server 提供两个主要服务：

1. **管理 API (Port 9000)** - 用于会话管理的 REST API
2. **WebSocket 服务 (Port 9001)** - 用于实时对话的 WebSocket 接口

## 🏗️ 架构

GPU Server 支持两种运行模式：

### 模式 1: 统一模式（推荐）

所有服务运行在同一个进程中，共享 SessionManager，确保会话状态一致。

```
┌─────────────────────────────────────────────────────────┐
│              GPU Server (Unified Mode)                  │
│              Port: 9000                                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────────────────────────────────┐ │
│  │         Unified Server (unified_server.py)        │ │
│  │  ┌──────────────────┐  ┌──────────────────┐    │ │
│  │  │ Management API    │  │ WebSocket Server │    │ │
│  │  │ /mgmt/v1/sessions│  │ /ws/ws/{session} │    │ │
│  │  │ (兼容: /v1/...)  │  │                  │    │ │
│  │  └──────────────────┘  └──────────────────┘    │ │
│  └──────────────────────────────────────────────────┘ │
│            │                         │                  │
│            └────────┬────────────────┘                  │
│                     │                                    │
│            ┌────────▼────────┐                          │
│            │ Session Manager │                          │
│            │  (共享内存)      │                          │
│            └────────┬────────┘                          │
│                     │                                    │
│            ┌────────▼────────┐                          │
│            │   AI Engine     │                          │
│            │ (LLM/ASR/TTS)   │                          │
│            └─────────────────┘                          │
└─────────────────────────────────────────────────────────┘
```

### 模式 2: 分开运行模式（已弃用）

管理 API 和 WebSocket 服务分开运行，各自有独立的 SessionManager 实例。

```
┌─────────────────────────────────────────────────────────┐
│                    GPU Server                            │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────┐   │
│  │   Management API     │  │  WebSocket Server    │   │
│  │   (FastAPI)          │  │  (FastAPI + WS)      │   │
│  │   Port: 9000         │  │  Port: 9001          │   │
│  └──────────────────────┘  └──────────────────────┘   │
│            │                         │                  │
│            └────────┬────────────────┘                  │
│                     │                                    │
│  ┌──────────▼────────┐  ┌──────────▼────────┐          │
│  │ Session Manager 1 │  │ Session Manager 2 │          │
│  │  (独立实例)        │  │  (独立实例)        │          │
│  └───────────────────┘  └───────────────────┘          │
│            │                         │                  │
│            └────────┬────────────────┘                  │
│                     │                                    │
│            ┌────────▼────────┐                          │
│            │   AI Engine     │                          │
│            │ (LLM/ASR/TTS)   │                          │
│            └─────────────────┘                          │
└─────────────────────────────────────────────────────────┘
```

**注意**：分开运行模式会导致 SessionManager 不共享，WebSocket 无法验证管理 API 创建的会话。**推荐使用统一模式**。

**重要说明**：
- **SessionManager 共享** ≠ **会话数据共享**
  - SessionManager 共享：管理 API 和 WebSocket 服务使用同一个 SessionManager 实例，可以互相看到对方创建的会话
  - 会话数据隔离：每个会话仍然是完全独立的，有独立的 `session_id`、`token`、`tutor_id`、`student_id`、`kb_id`
  - 不同客户端的会话互不干扰，数据完全隔离
- **AI 模型隔离**：
  - **当前实现**：按 `tutor_id` 隔离模型实例
  - **模型实例**：每个 `tutor_id` 对应一个独立的 AIEngine 实例
  - **实例缓存**：模型实例会被缓存，同一 `tutor_id` 复用同一个实例
  - **内存管理**：支持动态创建和清理模型实例
  - **上下文隔离**：每个会话的上下文通过 `session_id`、`tutor_id`、`kb_id` 参数区分
  - **数据隔离**：不同 tutor 的模型实例完全独立，不同会话的对话历史不会混淆
  
  **实现方式**：
  ```python
  # 获取指定 tutor_id 的 AI 引擎实例
  ai_engine = get_ai_engine(tutor_id=1)  # Tutor 1 的模型实例
  ai_engine = get_ai_engine(tutor_id=2)  # Tutor 2 的模型实例（不同的实例）
  ```
  
  **优势**：
  - 不同 tutor 可以使用不同的模型配置
  - 支持按 tutor 动态加载不同的 LLM/ASR/TTS 模型
  - 模型实例按需创建，节省内存

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并根据需要修改：

```bash
cp .env.example .env
```

### 3. 启动服务

#### 方式一：统一模式（推荐）

```bash
python3 unified_server.py
```

**统一模式特点：**
- 所有服务运行在同一进程（Port 9000）
- SessionManager 共享，确保会话状态一致
- 路径兼容层：`/v1/sessions` 自动转发到 `/mgmt/v1/sessions`
- WebSocket 路径：`ws://localhost:9000/ws/ws/{session_id}`

**访问地址：**
- 管理 API: `http://localhost:9000/mgmt/v1/sessions`
- 管理 API (兼容): `http://localhost:9000/v1/sessions`
- WebSocket: `ws://localhost:9000/ws/ws/{session_id}`
- API 文档: `http://localhost:9000/docs`

#### 方式二：分开运行模式（已弃用）

```bash
./start.sh
```

这会启动两个独立服务：
- 管理 API: http://localhost:9000
- WebSocket API: ws://localhost:9001

**注意**：分开运行模式会导致 SessionManager 不共享，WebSocket 无法验证管理 API 创建的会话。

### 4. 查看 API 文档

访问 http://localhost:9000/docs 查看交互式 API 文档 (Swagger UI)

### 5. 停止服务

**统一模式：**
```bash
pkill -f unified_server.py
```

**分开运行模式：**
```bash
./stop.sh
```

## 📡 API 接口

### 管理 API (Port 9000)

#### 1. 健康检查

```http
GET /health
```

响应：
```json
{
  "status": "healthy",
  "service": "GPU Server Management API",
  "active_sessions": 0,
  "max_sessions": 10
}
```

#### 2. 创建会话

```http
POST /v1/sessions
Content-Type: application/json

{
  "tutor_id": 1,
  "student_id": 1,
  "kb_id": "optional-knowledge-base-id"
}
```

响应：
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "engine_url": "ws://localhost:9000/ws/ws/550e8400-e29b-41d4-a716-446655440000",
  "engine_token": "xxxxxxxxxxxxxxxxxxx",
  "status": "active"
}
```

**注意**：
- **统一模式**：`engine_url` 格式为 `ws://host:9000/ws/ws/{session_id}`
- **分开模式**：`engine_url` 格式为 `ws://host:9001/ws/{session_id}`
- 推荐使用统一模式，确保 SessionManager 共享

#### 3. 查询会话状态

```http
GET /v1/sessions/{session_id}
```

响应：
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "tutor_id": 1,
  "student_id": 1,
  "kb_id": null,
  "status": "active",
  "created_at": "2024-12-22T12:00:00",
  "last_activity": "2024-12-22T12:05:00"
}
```

#### 4. 结束会话

```http
DELETE /v1/sessions/{session_id}
```

响应：204 No Content

#### 5. 列出所有会话（调试用）

```http
GET /v1/sessions
```

### WebSocket API

#### 连接（统一模式）

```
ws://localhost:9000/ws/ws/{session_id}?token={engine_token}
```

#### 连接（分开运行模式 - 已弃用）

```
ws://localhost:9001/ws/{session_id}?token={engine_token}
```

参数：
- `session_id`: 会话 ID（从创建会话接口获取）
- `token`: engine_token（用于认证）

#### 消息格式

**客户端 → 服务器（文本消息）：**
```json
{
  "type": "text",
  "content": "你好，请问什么是Python？"
}
```

**客户端 → 服务器（音频消息）：**
```json
{
  "type": "audio",
  "data": "base64编码的音频数据"
}
```

**服务器 → 客户端（文本响应）：**
```json
{
  "type": "text",
  "content": "Python 是一种高级编程语言...",
  "role": "assistant",
  "timestamp": "2024-12-22T12:00:00"
}
```

**服务器 → 客户端（转录结果）：**
```json
{
  "type": "transcription",
  "content": "你好，请问什么是Python？",
  "role": "user",
  "timestamp": "2024-12-22T12:00:00"
}
```

**服务器 → 客户端（音频响应）：**
```json
{
  "type": "audio",
  "content": "Python 是一种高级编程语言...",
  "data": "base64编码的音频数据",
  "role": "assistant",
  "timestamp": "2024-12-22T12:00:00"
}
```

**服务器 → 客户端（错误消息）：**
```json
{
  "type": "error",
  "content": "错误描述",
  "timestamp": "2024-12-22T12:00:00"
}
```

## 🔧 配置说明

### 环境变量（.env）

```bash
# 管理 API 配置
MANAGEMENT_API_HOST=0.0.0.0
MANAGEMENT_API_PORT=9000

# WebSocket 配置
WEBSOCKET_HOST=0.0.0.0
WEBSOCKET_PORT=9001
WEBSOCKET_URL=ws://localhost:9001

# GPU 配置
CUDA_VISIBLE_DEVICES=0

# 会话配置
MAX_SESSIONS=10
SESSION_TIMEOUT_SECONDS=3600
```

### 配置项说明

- `MANAGEMENT_API_HOST/PORT`: 管理 API 监听地址和端口
- `WEBSOCKET_HOST/PORT`: WebSocket 服务监听地址和端口
- `WEBSOCKET_URL`: 返回给客户端的 WebSocket URL（公网地址）
- `CUDA_VISIBLE_DEVICES`: 可用的 GPU 设备
- `MAX_SESSIONS`: 最大并发会话数
- `SESSION_TIMEOUT_SECONDS`: 会话超时时间（秒）

## 📁 文件结构

```
gpuserver/
├── unified_server.py        # 统一服务器（推荐使用）
├── management_api.py        # 管理 API 服务
├── websocket_server.py      # WebSocket 服务
├── session_manager.py       # 会话管理器
├── ai_models.py             # AI 模型接口（Mock 实现）
├── config.py                # 配置管理
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量示例
├── .env                     # 环境变量配置
├── start.sh                 # 启动脚本（分开运行模式）
├── stop.sh                  # 停止脚本
├── test_server.py           # 功能测试脚本
├── test_websocket.py        # WebSocket 测试脚本
├── test_connectivity.sh     # 连通性测试脚本
└── README.md                # 本文档
```

## 🧪 测试

### 快速测试脚本

项目提供了多个测试脚本，方便快速验证功能：

#### 1. 连通性测试

```bash
# 测试本地服务和 FRP 连通性
./test_connectivity.sh
```

测试内容：
- 本地服务健康检查
- FRP 客户端状态
- 远程访问测试
- 会话创建测试

#### 2. 功能测试

```bash
# 测试管理 API 和 WebSocket 基本功能
python3 test_server.py
```

测试内容：
- 健康检查
- 创建会话
- 查询会话状态
- 删除会话
- WebSocket 服务健康检查

#### 3. WebSocket 实时连接测试

```bash
# 测试 WebSocket 实时连接和消息处理
python3 test_websocket.py
```

测试内容：
- WebSocket 连接
- 文本消息发送和接收
- 音频消息处理流程
- 错误处理（无效 token、无效消息类型等）

#### 4. 最大会话数限制测试

```bash
# 测试会话数限制功能
python3 << 'EOF'
import requests

base_url = "http://localhost:9000"
max_sessions = 10

# 创建会话直到达到上限
for i in range(max_sessions + 1):
    response = requests.post(
        f"{base_url}/v1/sessions",
        json={"tutor_id": 1, "student_id": i+1}
    )
    if response.status_code == 201:
        print(f"✓ 创建会话 {i+1}")
    elif response.status_code == 503:
        print(f"✓ 达到上限: {response.json()['detail']}")
        break
EOF
```

### 手动测试

#### 测试管理 API

```bash
# 健康检查
curl http://localhost:9000/health

# 创建会话（统一模式 - 兼容路径）
curl -X POST http://localhost:9000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 1, "kb_id": "test-kb"}'

# 创建会话（统一模式 - 原始路径）
curl -X POST http://localhost:9000/mgmt/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 1, "kb_id": "test-kb"}'

# 查询会话（替换 {session_id}）
curl http://localhost:9000/v1/sessions/{session_id}

# 删除会话
curl -X DELETE http://localhost:9000/v1/sessions/{session_id}

# 列出所有会话
curl http://localhost:9000/v1/sessions
```

#### 测试 WebSocket

**使用 Python 测试脚本（推荐）：**

```bash
python3 test_websocket.py
```

**使用 wscat 工具测试：**

```bash
# 安装 wscat（如果未安装）
npm install -g wscat

# 先创建会话获取 session_id 和 token
SESSION_RESPONSE=$(curl -X POST http://localhost:9000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 1}')

# 提取 session_id 和 token
SESSION_ID=$(echo $SESSION_RESPONSE | jq -r '.session_id')
TOKEN=$(echo $SESSION_RESPONSE | jq -r '.engine_token')
ENGINE_URL=$(echo $SESSION_RESPONSE | jq -r '.engine_url')

# 连接 WebSocket（统一模式）
wscat -c "${ENGINE_URL}?token=${TOKEN}"

# 发送测试消息
> {"type": "text", "content": "你好"}
```

### 测试路径总结

| 测试项 | 本地路径 | 远程路径（FRP） | 测试脚本 |
|--------|---------|----------------|---------|
| 健康检查 | `http://localhost:9000/health` | `http://51.161.130.234:19000/health` | `test_connectivity.sh` |
| 创建会话 | `POST /v1/sessions` | `POST http://51.161.130.234:19000/v1/sessions` | `test_server.py` |
| 查询会话 | `GET /v1/sessions/{id}` | `GET http://51.161.130.234:19000/v1/sessions/{id}` | `test_server.py` |
| WebSocket | `ws://localhost:9000/ws/ws/{id}` | `ws://51.161.130.234:19001/ws/ws/{id}` | `test_websocket.py` |
| 会话限制 | `POST /v1/sessions` (多次) | - | 手动测试 |

## 🔄 与 Web Server 对接

### Web Server 端集成

1. **创建会话**：Web Server 在学生登录时调用 `POST /v1/sessions` 创建会话
2. **返回连接信息**：将 `engine_url` 和 `engine_token` 返回给前端
3. **前端直连**：前端使用这些信息直接连接到 WebSocket 进行实时对话

### 前端集成示例

```javascript
// 1. 从 Web Server 获取会话信息
const response = await fetch('/api/student/sessions', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: JSON.stringify({ tutor_id: 1 })
});

const { engine_url, engine_token } = await response.json();

// 2. 连接到 GPU Server WebSocket
const ws = new WebSocket(`${engine_url}?token=${engine_token}`);

ws.onopen = () => {
  console.log('Connected to AI tutor');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);

  if (message.type === 'text') {
    // 显示 AI 响应
    displayMessage(message.content);
  }
};

// 3. 发送消息
function sendMessage(text) {
  ws.send(JSON.stringify({
    type: 'text',
    content: text
  }));
}
```

## 🚧 当前状态

### ✅ 已实现

- [x] 管理 API (Port 9000)
  - [x] 健康检查
  - [x] 创建会话
  - [x] 查询会话状态
  - [x] 结束会话
  - [x] 列出所有会话
- [x] WebSocket 服务 (Port 9001)
  - [x] Token 认证
  - [x] 文本消息处理
  - [x] 音频消息处理
  - [x] 错误处理
- [x] 会话管理器
  - [x] 会话创建和删除
  - [x] Token 生成和验证
  - [x] 会话超时清理
- [x] AI 模型接口（Mock 实现）
  - [x] LLM 文本生成
  - [x] ASR 语音转文本
  - [x] TTS 文本转语音

### 🔨 待实现（生产环境）

- [ ] 真实 AI 模型集成
  - [ ] LLM 模型加载和推理
  - [ ] ASR 模型集成
  - [ ] TTS 模型集成
  - [ ] MuseTalk 视频生成
- [ ] RAG 知识库检索
- [ ] 性能优化
  - [ ] 批处理推理
  - [ ] 模型缓存
  - [ ] GPU 内存管理
- [ ] 监控和日志
  - [ ] 推理性能监控
  - [ ] 错误追踪
  - [ ] 资源使用监控

## 📝 注意事项

1. **Mock 模式**：当前 AI 模型使用 Mock 实现，仅用于接口测试
2. **Token 安全**：`engine_token` 仅用于会话验证，不包含敏感信息
3. **会话清理**：过期会话会自动清理，默认超时时间为 1 小时
4. **并发限制**：默认最大并发会话数为 10，可通过配置调整

## 🤝 贡献

如需添加真实 AI 模型实现，请修改 [ai_models.py](ai_models.py) 中的 `AIEngine` 类。

## 📄 许可

本项目是 Virtual Tutor System 的一部分。

---

---

**最后更新**: 2025-12-23

## 📚 更新日志

### 2025-12-23 (最新)
- ✅ 实现按 tutor_id 隔离模型实例
  - 每个 tutor_id 对应一个独立的 AIEngine 实例
  - 模型实例缓存和管理机制
  - 支持动态创建和清理模型实例
  - 线程安全的实例创建
  - 测试通过：不同 tutor 使用不同的模型实例

### 2025-12-23
- ✅ 实现统一模式（`unified_server.py`）
- ✅ 添加路径兼容层（`/v1/sessions` → `/mgmt/v1/sessions`）
- ✅ 修复 SessionManager 共享问题
- ✅ 添加测试脚本（`test_server.py`, `test_websocket.py`, `test_connectivity.sh`）
- ✅ 更新文档，添加统一模式启动流程和测试路径
