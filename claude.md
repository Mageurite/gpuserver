# Virtual Tutor System - AI 助手上下文文档

> 本文档为 AI 助手提供项目核心上下文，帮助快速理解项目结构和关键信息。

## 📋 项目概述

Virtual Tutor System 是一个基于 Sozio.AI 的多租户虚拟导师平台，用于为教师/管理员创建专属的「虚拟导师」，并通过唯一 URL 分发给学生使用。学生通过实时语音/视频/文本与 AI 导师互动。

### 🤖 AI 助手角色说明

**当前角色：GPU Server 开发者**

- **我的任务**：参照 `try/` 目录下的参考代码，开发完整的 GPU Server 实现，并与前端成功对接
- **参考代码**：`try/` 目录是完全可运行的参考实现，**不要修改它**，仅作为参考
- **工作目标**：
  1. 实现 GPU Server 的管理 API (Port 9000)
  2. 实现 GPU Server 的 WebSocket 实时接口
  3. 实现会话管理和 AI 模型推理逻辑
  4. 确保与前端完全对接，实现端到端的实时对话功能

### 核心特性

- **多租户架构**：Admin → Tutor → Student 三级结构
- **实时对话**：支持文本、语音、视频多种交互方式
- **RAG 知识库**：每个 Tutor 可上传专属文档，支持知识检索
- **权限隔离**：严格的多租户数据隔离

---

## 🏗️ 系统架构

### 双服务器架构

```
┌─────────────────────────────────────────┐
│         Server A (Web Server)           │
│  ┌────────────────────────────────────┐ │
│  │ React Frontend (Port 3000)         │ │
│  │ FastAPI Backend (Port 8000)        │ │
│  │ (认证、管理、数据存储)              │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
         │ HTTP API      │ WebSocket
         ▼               ▼
┌─────────────────────────────────────────┐
│       Serverless (GPU Server)           │
│  ┌──────────────┐  ┌──────────────┐   │
│  │ AI Engine 1  │  │ AI Engine 2  │   │
│  │ - LLM        │  │ - LLM        │   │
│  │ - ASR/TTS    │  │ - ASR/TTS    │   │
│  │ - MuseTalk   │  │ - MuseTalk   │   │
│  └──────────────┘  └──────────────┘   │
│  Management API: Port 9000              │
└─────────────────────────────────────────┘
```

### 数据流

1. **控制面**：Web Server → `POST /v1/sessions` → 返回 `engine_url` + `engine_token`
2. **数据面**：前端 → `ws://gpu-server:9000/ws/ws/{session_id}?token={token}` → 实时对话
3. **会话结束**：Web Server → `DELETE /v1/sessions/{id}` → 清理资源

---

## 🛠️ 技术栈

### Web Server
- FastAPI 0.122.0 + SQLAlchemy 2.0.44 + React 19.1.0
- 职责：认证、管理、数据持久化

### GPU Server
- FastAPI 0.115.0 + Uvicorn + WebSockets
- LLM：Ollama（langchain-ollama），支持按 tutor_id 配置不同模型
- ASR/TTS：待集成（当前 Mock）
- MuseTalk：待集成
- 职责：AI 推理、实时对话处理

---

## 🎯 GPU Server 开发重点

### 架构模式

**统一模式**（推荐）：所有服务运行在同一进程（Port 9000），管理 API 和 WebSocket 服务共享 SessionManager

### 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| 主入口 | `unified_server.py` | 集成所有服务 |
| 管理 API | `management_api.py` | 会话 CRUD |
| WebSocket | `websocket_server.py` | 实时对话 |
| 会话管理 | `session_manager.py` | 会话生命周期 |
| AI 引擎 | `ai_models.py` | AI 推理接口 |
| LLM | `llm/llm_engine.py` | Ollama 集成 |
| 配置 | `config.py` | 环境变量管理 |

### API 接口

#### 管理 API (Port 9000)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/v1/sessions` | POST | 创建会话 |
| `/v1/sessions/{id}` | GET | 查询会话 |
| `/v1/sessions/{id}` | DELETE | 结束会话 |

**创建会话请求**：
```json
{"tutor_id": 1, "student_id": 123, "kb_id": "kb-001"}
```

**创建会话响应**：
```json
{
  "session_id": "uuid",
  "engine_url": "ws://localhost:9000/ws/ws/uuid",
  "engine_token": "token",
  "status": "active"
}
```

#### WebSocket (Port 9000, 路径: `/ws/ws/{session_id}`)

**客户端发送**：
```json
{"type": "text", "content": "你好"}
{"type": "audio", "data": "base64..."}
```

**服务器返回**：
```json
{"type": "text", "content": "回复内容", "role": "assistant", "timestamp": "..."}
{"type": "audio", "content": "...", "data": "base64...", "role": "assistant"}
{"type": "transcription", "content": "转录文本", "role": "user"}
{"type": "error", "content": "错误信息"}
```

### 实现进度

| 模块 | 状态 | 说明 |
|------|------|------|
| 统一服务器 | ✅ 完成 | 单进程运行 |
| 管理 API | ✅ 完成 | 会话 CRUD |
| WebSocket | ✅ 完成 | 实时对话 |
| 会话管理 | ✅ 完成 | Token 验证、超时清理 |
| LLM 集成 | ✅ 完成 | Ollama + 多模型支持 |
| 模型隔离 | ✅ 完成 | 按 tutor_id 隔离 |
| ASR/TTS | 🚧 Mock | 待集成 |
| MuseTalk | 🚧 待集成 | 代码在 `/workspace/MuseTalk/` |
| RAG 检索 | 🚧 待实现 | 预留接口 |

---

## 🔧 关键配置

### GPU Server 环境变量

```bash
# gpuserver/.env

# 服务器配置
MANAGEMENT_API_HOST=0.0.0.0
MANAGEMENT_API_PORT=9000
WEBSOCKET_URL=ws://localhost:9000

# 会话管理
MAX_SESSIONS=10
SESSION_TIMEOUT_SECONDS=3600

# LLM 配置
OLLAMA_BASE_URL=http://127.0.0.1:11434
DEFAULT_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16
LLM_TEMPERATURE=0.4
ENABLE_LLM=true

# 按 Tutor 配置不同模型
TUTOR_1_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16
TUTOR_2_LLM_MODEL=llama3.1:8b-instruct-q4_K_M
```

### 网络配置场景

| 场景 | Web Server `ENGINE_URL` | GPU Server `WEBSOCKET_URL` |
|------|-------------------------|----------------------------|
| 本地开发 | `http://127.0.0.1:9000` | `ws://127.0.0.1:9000` |
| 局域网 | `http://192.168.1.100:9000` | `ws://192.168.1.100:9000` |
| 公网 | `http://gpu-public-ip:9000` | `ws://gpu-public-ip:9000` |
| FRP | `http://gpu-server.frp.example.com` | - |

---

## 📦 代码目录说明

```
/workspace/
├── gpuserver/          # GPU Server 实现 ✅ 提交
│   ├── unified_server.py
│   ├── management_api.py
│   ├── websocket_server.py
│   ├── session_manager.py
│   ├── ai_models.py
│   ├── config.py
│   ├── llm/
│   │   ├── llm_engine.py
│   │   └── __init__.py
│   ├── temp/
│   │   ├── scripts/        # 启动/停止脚本
│   │   └── tests/          # 测试脚本
│   ├── .env.example
│   └── requirements.txt
│
├── MuseTalk/           # 视频生成模型 ✅ 可提交
│
├── try/                # 参考代码 ❌ 不要修改，不要提交
│   ├── llm/            # LLM 参考实现
│   ├── rag/            # RAG 参考实现
│   ├── tts/            # TTS 参考实现
│   └── lip-sync/       # MuseTalk 参考实现
│
└── virtual_tutor/      # Web Server ❌ 不要提交
```

---

## 🚀 快速开发指南

### 1. 环境准备
```bash
cd /workspace/gpuserver
export PATH="/workspace/conda_envs/rag/bin:$PATH"  # 使用 try 的 conda 环境
# 或
pip install -r requirements.txt
```

### 2. 配置
```bash
cp .env.example .env
vim .env  # 修改配置
```

### 3. 启动 GPU Server
```bash
bash temp/scripts/start_server.sh
# 或
python3 unified_server.py
```

### 4. 连接 Web Server

#### 方式一：本地同机部署（推荐用于开发测试）

```bash
# 1. 确认 GPU Server 正在运行
curl http://localhost:9000/health

# 2. 配置 Web Server
cd /workspace/virtual_tutor/app_backend
vim .env
# 确保包含：ENGINE_URL=http://localhost:9000

# 3. 启动 Web Server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 4. 测试连接（Web Server 会自动连接 GPU Server）
curl http://localhost:8000/health
```

#### 方式二：局域网部署（GPU Server 和 Web Server 在不同机器）

```bash
# GPU Server 机器（IP: 192.168.1.100）
cd /workspace/gpuserver
python3 unified_server.py

# Web Server 机器
cd /path/to/webserver/app_backend
vim .env  # 修改为：ENGINE_URL=http://192.168.1.100:9000
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### 验证连接

```bash
# 测试 GPU Server
curl http://<gpu-server-ip>:9000/health

# 通过 Web Server 创建会话（会调用 GPU Server）
curl -X POST http://localhost:8000/api/student/sessions \
  -H "Authorization: Bearer <your-jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 123}'
```

### 5. 测试 GPU Server
```bash
curl http://localhost:9000/health
curl -X POST http://localhost:9000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 123}'

python3 temp/tests/test_server.py
python3 temp/tests/test_websocket.py
python3 temp/tests/test_llm.py
```

### 6. 停止服务
```bash
# 停止 GPU Server
bash temp/scripts/stop_server.sh

# 停止 Web Server
pkill -f "uvicorn app.main:app"
```

---

## ❓ 常见问题

### Q1: LLM 调用失败？
1. 确认 Ollama 运行：`curl http://127.0.0.1:11434/api/tags`
2. 确认模型已安装：`ollama pull mistral-nemo:12b-instruct-2407-fp16`
3. 检查环境变量：`ENABLE_LLM=true`, `OLLAMA_BASE_URL` 正确

### Q2: WebSocket 连接失败？
1. 确认服务运行：`curl http://localhost:9000/health`
2. 路径正确：`ws://localhost:9000/ws/ws/{session_id}?token={token}`（注意两个 `ws`）
3. Token 有效：先调用管理 API 创建会话获取 token

### Q3: 如何为不同 Tutor 配置不同模型？
在 `.env` 中添加：`TUTOR_{id}_LLM_MODEL=模型名称`

### Q4: 会话数达到上限？
1. 增加限制：`MAX_SESSIONS=20`
2. 调整超时：`SESSION_TIMEOUT_SECONDS=1800`

### Q5: GPU Server 无法连接到 Web Server？

**症状**：Web Server 创建会话时报错，或者无法调用 GPU Server

**解决方案**：

1. **确认 GPU Server 正在运行**：
   ```bash
   curl http://localhost:9000/health
   # 应该返回：{"status": "healthy", ...}
   ```

2. **检查 Web Server 配置**：
   ```bash
   cd /workspace/virtual_tutor/app_backend
   cat .env | grep ENGINE_URL
   # 应该显示：ENGINE_URL=http://localhost:9000（本地）
   # 或：ENGINE_URL=http://192.168.1.100:9000（局域网）
   ```

3. **测试网络连通性**：
   ```bash
   # 从 Web Server 机器测试
   curl http://<gpu-server-ip>:9000/health

   # 如果连接失败，检查防火墙
   sudo ufw allow 9000/tcp
   ```

4. **查看 Web Server 日志**：
   ```bash
   # Web Server 启动日志会显示是否连接到 GPU Server
   # 如果 ENGINE_URL 未配置，会使用 Mock 模式
   ```

5. **完整测试流程**：
   ```bash
   # 1. 启动 GPU Server
   cd /workspace/gpuserver
   python3 unified_server.py

   # 2. 在另一个终端启动 Web Server
   cd /workspace/virtual_tutor/app_backend
   uvicorn app.main:app --host 0.0.0.0 --port 8000

   # 3. 测试端到端连接
   # 先登录获取 token
   curl -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "admin@example.com", "password": "admin123"}'

   # 使用返回的 token 创建会话
   curl -X POST http://localhost:8000/api/student/sessions \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"tutor_id": 1, "student_id": 123}'

   # 应该返回包含 engine_url 的响应
   ```

### Q6: 如何添加 ASR/TTS？
修改 `ai_models.py` 中的 `process_audio()` 和 `synthesize_speech()` 方法，参考 `try/` 目录实现

---

## 📚 参考资源

- [GPU Server README](gpuserver/README.md)：详细文档
- [LLM README](gpuserver/llm/README.md)：LLM 模块说明
- `try/llm/`：LLM 参考实现
- `try/rag/`：RAG 参考实现
- `try/tts/`：TTS 参考实现
- `try/lip-sync/`：MuseTalk 参考实现

---

**最后更新**：2025-12-23
