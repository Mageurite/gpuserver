# GPU Server - AI 推理引擎

这是 Virtual Tutor System 的 GPU Server 实现，负责处理 AI 推理和实时对话。

---

## 📚 快速导航

**新用户必读**：
- 🚀 **[快速启动指南](README_QUICKSTART.md)** - 5分钟快速上手
- 🔧 **[FRP 故障排查](FRP_TROUBLESHOOTING.md)** - FRP 连接问题解决方案

**主要文档**：
- 📖 本文档 - GPU Server 完整使用说明
- 📋 [项目介绍](../项目介绍.md) - 整体架构说明

---

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

⚠️ **注意**：分开运行模式会导致 SessionManager 不共享，WebSocket 无法验证管理 API 创建的会话，不推荐使用。

## 🚀 快速开始

### 推荐启动方式 ⭐

```bash
cd /workspace/gpuserver

# 方式 1: 一键启动所有服务（推荐）
./start_all.sh
# 在提示时选择 Y 启动 FRP 内网穿透

# 方式 2: 基础启动
./start.sh
# 在提示时选择是否启动 FRP

# 方式 3: 只启动 FRP
./start_frpc.sh --force
```

**启动脚本对比**：
| 脚本 | 用途 | 特点 |
|------|------|------|
| `./start_all.sh` | 一键启动 | 最完整，推荐使用 |
| `./start.sh` | 基础启动 | 支持选择是否启动 FRP |
| `./start_frpc.sh` | 只启动 FRP | 防止重复启动，自动清理 |

**查看状态**：
```bash
# 查看进程
ps aux | grep -E "unified_server|frpc"

# 查看日志
tail -f logs/unified_server.log  # GPU Server
tail -f logs/frpc.log             # FRP

# 健康检查
curl http://localhost:9000/health              # 本地
curl http://51.161.130.234:19000/health       # 外网
```

**停止服务**：
```bash
./stop_all.sh     # 停止所有服务
./stop.sh         # 停止 GPU Server（会询问是否停止 FRP）
./stop_frpc.sh    # 只停止 FRP
```

### 详细配置步骤

### 1. 安装依赖

#### 方式一：使用 try 目录的 conda 环境（推荐）

LLM 和 RAG 共用 `conda_envs/rag` 环境，可以直接使用：

```bash
# 使用 rag 环境的 Python（已包含 langchain-ollama 等依赖）
export PATH="/workspace/conda_envs/rag/bin:$PATH"

# 或者直接使用完整路径
/workspace/conda_envs/rag/bin/python unified_server.py
```

#### 方式二：安装到当前环境

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并根据需要修改：

```bash
cp .env.example .env
```

### 3. 启动服务

#### 方式一：使用启动脚本（推荐）⭐

```bash
# 启动服务
./start.sh

# 查看状态
./status.sh

# 停止服务
./stop.sh

# 重启服务
./restart.sh
```

**启动脚本特点：**
- 自动检查并复制 `.env` 配置文件
- 自动选择最佳 Python 环境（优先使用 conda）
- 自动检查依赖并安装
- 后台运行并保存日志
- 自动进行健康检查
- 保存进程 PID 便于管理

#### 方式二：手动启动

```bash
# 使用 rag conda 环境
export PATH="/workspace/conda_envs/rag/bin:$PATH"
python3 unified_server.py
```

或者直接使用完整路径：

```bash
/workspace/conda_envs/rag/bin/python unified_server.py
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
bash temp/scripts/start.sh
```

这会启动两个独立服务：
- 管理 API: http://localhost:9000
- WebSocket API: ws://localhost:9001

⚠️ **警告**：分开运行模式会导致 SessionManager 不共享，WebSocket 无法验证管理 API 创建的会话。

### 4. 停止服务

```bash
# 使用停止脚本（推荐）
./stop.sh

# 或手动停止
pkill -f "python.*unified_server.py"
```

### 5. 查看服务状态

```bash
# 查看详细状态信息
./status.sh

# 查看日志
tail -f logs/server.log
```

### 6. 测试与 Web Server 的连接

```bash
# 测试 GPU Server 和 Web Server 的连通性
./test_webserver_connection.sh
```

这个脚本会：
- 检查 GPU Server 是否运行
- 检查 Web Server 是否运行
- 验证 Web Server 的 ENGINE_URL 配置
- 测试创建会话、查询会话、WebSocket 连接
- 提供配置建议

## ⚙️ 配置说明

### 环境变量

在 `.env` 文件中配置：

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

# LLM 配置
OLLAMA_BASE_URL=http://127.0.0.1:11434
DEFAULT_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16
LLM_TEMPERATURE=0.4
ENABLE_LLM=true

# 按 tutor_id 配置不同模型（可选）
TUTOR_1_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16
TUTOR_2_LLM_MODEL=llama3.1:8b-instruct-q4_K_M
```

### LLM 依赖说明

**推荐方式**：使用 `try` 目录的 `conda_envs/rag` 环境，该环境已包含所有 LLM 相关依赖：
- `langchain-ollama`
- `langchain-core`
- `langchain`

如果使用自己的环境，需要安装：
```bash
pip install langchain langchain-core langchain-ollama
```

## 📁 文件结构

```
gpuserver/
├── unified_server.py        # 统一服务器（推荐使用）⭐
├── management_api.py        # 管理 API 服务
├── websocket_server.py      # WebSocket 服务
├── session_manager.py       # 会话管理器
├── ai_models.py             # AI 模型接口
├── llm/                     # LLM 模块
│   ├── __init__.py
│   ├── llm_engine.py        # LLM 引擎实现
│   └── README.md
├── config.py                # 配置管理
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量示例
├── frpc.ini                  # FRP 客户端配置
├── temp/                    # 脚本和测试文件
│   ├── scripts/             # 启动、停止、安装脚本
│   │   ├── start.sh                 # 启动脚本（分开运行模式，已弃用）
│   │   ├── start_server.sh          # 启动脚本（宿主机版本）⭐
│   │   ├── start_frpc.sh            # 启动 FRP 客户端
│   │   ├── start_with_frp.sh        # 快速启动（带 FRP）
│   │   ├── stop.sh                  # 停止脚本
│   │   ├── stop_server.sh           # 停止服务器
│   │   ├── stop_frpc.sh              # 停止 FRP 客户端
│   │   ├── install_frpc.sh          # 安装 FRP 客户端
│   │   └── test_connectivity.sh     # 连通性测试脚本
│   └── tests/               # 测试脚本
│       ├── test_server.py           # 功能测试脚本
│       ├── test_websocket.py        # WebSocket 测试脚本
│       └── test_llm.py              # LLM 测试脚本
└── README.md                # 本文档
```

## 🧪 测试

### 快速测试脚本

项目提供了多个测试脚本，方便快速验证功能：

#### 1. 连通性测试

```bash
# 测试本地服务和 FRP 连通性
bash temp/scripts/test_connectivity.sh
```

测试内容：
- 本地服务健康检查
- FRP 客户端状态
- 远程访问测试
- 会话创建测试

#### 2. 功能测试

```bash
# 测试管理 API 和 WebSocket 基本功能
python3 temp/tests/test_server.py
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
python3 temp/tests/test_websocket.py
```

测试内容：
- WebSocket 连接
- 文本消息发送和接收
- 音频消息处理流程
- 错误处理（无效 token、无效消息类型等）

#### 4. 最大会话数限制测试

```bash
# 测试会话数限制功能
python3 temp/tests/test_server.py
# 在测试输出中查看会话数限制测试结果
```

#### 5. LLM 功能测试

```bash
# 使用 rag conda 环境测试 LLM
export PATH="/workspace/conda_envs/rag/bin:$PATH"
python3 temp/tests/test_llm.py
```

测试内容：
- LLM 基本文本生成
- 多 Tutor 模型隔离
- Mock 模式降级

## 📝 API 接口

### 管理 API

#### 创建会话

```http
POST /v1/sessions
Content-Type: application/json

{
  "tutor_id": 1,
  "student_id": 123,
  "kb_id": "kb-001"  // 可选
}
```

响应：
```json
{
  "session_id": "uuid",
  "engine_url": "ws://localhost:9000/ws/ws/{session_id}",
  "engine_token": "token",
  "status": "active"
}
```

#### 查询会话状态

```http
GET /v1/sessions/{session_id}
```

#### 删除会话

```http
DELETE /v1/sessions/{session_id}
```

### WebSocket API

连接地址：
```
ws://localhost:9000/ws/ws/{session_id}?token={engine_token}
```

发送消息：
```json
{
  "type": "text",
  "content": "你好"
}
```

接收消息：
```json
{
  "type": "text",
  "content": "你好！我是虚拟导师助手。",
  "role": "assistant",
  "timestamp": "2025-12-23T..."
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
- [x] AI 模型接口
  - [x] LLM 文本生成（✅ 已集成 Ollama，支持真实 LLM 调用）
  - [x] ASR 语音转文本（Mock 实现）
  - [x] TTS 文本转语音（Mock 实现）

### 🔨 待实现（生产环境）

- [ ] 真实 AI 模型集成
  - [x] LLM 模型加载和推理（✅ 已实现，使用 Ollama）
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

1. **LLM 模式**：
   - 推荐使用 `conda_envs/rag` 环境（已包含所有依赖）
   - 默认启用真实 LLM（通过 Ollama）
   - 如果 Ollama 不可用或 `ENABLE_LLM=false`，会自动降级到 Mock 模式
   - 确保 Ollama 服务运行：`ollama serve`
   - 确保已安装模型：`ollama pull mistral-nemo:12b-instruct-2407-fp16`
2. **按 Tutor 配置模型**：可以通过环境变量 `TUTOR_{tutor_id}_LLM_MODEL` 为不同 tutor 配置不同模型
3. **Token 安全**：`engine_token` 仅用于会话验证，不包含敏感信息
4. **会话清理**：过期会话会自动清理，默认超时时间为 1 小时
5. **并发限制**：默认最大并发会话数为 10，可通过配置调整

## 🤝 贡献

如需添加真实 AI 模型实现，请修改 [ai_models.py](ai_models.py) 中的 `AIEngine` 类。

## 📄 许可

本项目是 Virtual Tutor System 的一部分。

---

---

**最后更新**: 2025-12-23

## 📚 更新日志

### 2025-12-24 (最新) 🎉
- ✅ **修复 FRP 连接问题**
  - 修复多进程冲突导致的连接不稳定
  - 修复配置文件路径错误
  - 修正日志路径配置
- ✅ **创建新的启动脚本**
  - `start_frpc.sh` - 改进的 FRP 启动脚本（防止重复启动）
  - `stop_frpc.sh` - 优雅停止脚本
- ✅ **更新主启动脚本**
  - `start.sh` / `stop.sh` - 支持选择是否启动/停止 FRP
  - `start_all.sh` / `stop_all.sh` - 集成 FRP 管理
- ✅ **废弃旧脚本**
  - `temp/scripts/start_frpc.sh` - 自动转向新脚本
  - `temp/scripts/start_with_frp.sh` - 自动转向新脚本
- ✅ **完善文档**
  - 新增 [FRP_TROUBLESHOOTING.md](FRP_TROUBLESHOOTING.md) - FRP 故障排查指南
  - 新增 [README_QUICKSTART.md](README_QUICKSTART.md) - 快速启动指南
  - 更新主 README 添加导航和脚本说明

### 2025-12-23
- ✅ 集成真实 LLM（Ollama）
  - 使用 `langchain-ollama` 集成 Ollama LLM
  - 支持按 tutor_id 配置不同模型（通过环境变量 `TUTOR_{tutor_id}_LLM_MODEL`）
  - 自动降级到 Mock 模式（如果 LLM 不可用或未安装依赖）
  - 保持接口兼容，无需修改调用代码
  - 添加测试脚本 `test_llm.py`
  - 更新配置项：`OLLAMA_BASE_URL`, `DEFAULT_LLM_MODEL`, `LLM_TEMPERATURE`, `ENABLE_LLM`
  - ✅ 支持使用 `try` 目录的 `conda_envs/rag` 环境（LLM 和 RAG 共用）

### 2025-12-23
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
