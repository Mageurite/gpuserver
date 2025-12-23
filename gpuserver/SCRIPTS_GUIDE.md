# GPU Server 服务管理脚本使用指南

本文档说明如何使用 GPU Server 的启动、停止和重启脚本。

## 📁 脚本列表

| 脚本 | 功能 | 说明 |
|------|------|------|
| `start.sh` | 启动服务 | 启动统一模式的 GPU Server（管理 API + WebSocket） |
| `stop.sh` | 停止服务 | 停止所有 GPU Server 相关进程 |
| `restart.sh` | 重启服务 | 先停止再启动服务 |

## 🚀 快速开始

### 1. 首次使用前准备

```bash
# 进入 gpuserver 目录
cd /workspace/gpuserver

# 确保脚本有执行权限（已自动设置）
chmod +x start.sh stop.sh restart.sh

# 复制环境变量配置文件（如果不存在）
cp .env.example .env

# 根据需要编辑配置
vim .env
```

### 2. 启动服务

```bash
# 启动 GPU Server
./start.sh
```

**启动脚本会自动：**
- 检查 `.env` 文件，如果不存在则从 `.env.example` 复制
- 检查是否已有服务在运行，避免重复启动
- 优先使用 conda 环境 `/workspace/conda_envs/rag`（如果存在）
- 检查必要的 Python 依赖
- 启动服务并后台运行
- 进行健康检查
- 保存进程 PID 到 `logs/server.pid`
- 输出服务访问地址

**输出示例：**
```
==========================================
  GPU Server - 启动服务
==========================================

检查 Python 环境...
使用 conda 环境: /workspace/conda_envs/rag
检查依赖...

正在启动 GPU Server...
  - 管理 API: http://0.0.0.0:9000/mgmt
  - 管理 API (兼容): http://0.0.0.0:9000/v1/sessions
  - WebSocket: ws://0.0.0.0:9000/ws/ws/{session_id}
  - API 文档: http://0.0.0.0:9000/docs

等待服务启动...
✓ GPU Server 启动成功 (PID: 12345)

查看日志: tail -f logs/server.log
停止服务: ./stop.sh
健康检查: curl http://localhost:9000/health

✓ 健康检查通过

==========================================
```

### 3. 停止服务

```bash
# 停止 GPU Server
./stop.sh
```

**停止脚本会自动：**
- 通过 PID 文件停止服务（优雅关闭）
- 检查并停止所有残留的相关进程
- 强制杀死无法正常停止的进程
- 检查端口是否已释放
- 清理 PID 文件

**输出示例：**
```
==========================================
  GPU Server - 停止服务
==========================================

正在停止 GPU Server...
停止进程 (PID: 12345)...
✓ GPU Server 已完全停止
✓ 端口 9000 已释放

==========================================
```

### 4. 重启服务

```bash
# 重启 GPU Server
./restart.sh
```

这相当于依次执行 `./stop.sh` 和 `./start.sh`。

## 📝 查看日志

服务日志保存在 `logs/server.log`：

```bash
# 实时查看日志
tail -f logs/server.log

# 查看最近 100 行日志
tail -n 100 logs/server.log

# 查看完整日志
cat logs/server.log
```

## ✅ 健康检查

启动服务后，可以进行健康检查：

```bash
# 检查服务状态
curl http://localhost:9000/health

# 应该返回：
# {"status":"healthy","service":"GPU Server"}

# 查看服务信息
curl http://localhost:9000/

# 测试管理 API
curl http://localhost:9000/mgmt/v1/sessions

# 测试兼容 API
curl http://localhost:9000/v1/sessions
```

## 🔍 故障排查

### 问题 1: 启动失败

**检查步骤：**
```bash
# 1. 查看日志
cat logs/server.log

# 2. 检查端口是否被占用
lsof -i :9000

# 3. 检查 Python 环境
which python3
python3 --version

# 4. 检查依赖
pip list | grep -E "fastapi|uvicorn|websockets"
```

### 问题 2: 无法停止服务

**解决方法：**
```bash
# 1. 查找所有相关进程
pgrep -af "unified_server.py"

# 2. 强制停止
pkill -9 -f "python.*unified_server.py"

# 3. 检查端口
lsof -i :9000

# 4. 强制释放端口（如果需要）
kill -9 $(lsof -t -i:9000)
```

### 问题 3: 环境变量未生效

**解决方法：**
```bash
# 1. 检查 .env 文件是否存在
ls -la .env

# 2. 检查 .env 内容
cat .env

# 3. 手动加载环境变量
export $(grep -v '^#' .env | xargs)

# 4. 重启服务
./restart.sh
```

### 问题 4: 权限问题

**解决方法：**
```bash
# 确保脚本有执行权限
chmod +x start.sh stop.sh restart.sh

# 确保 logs 目录可写
mkdir -p logs
chmod 755 logs
```

## ⚙️ 配置说明

在 `.env` 文件中可以配置以下参数：

```bash
# 服务器配置
MANAGEMENT_API_HOST=0.0.0.0        # 监听地址
MANAGEMENT_API_PORT=9000           # 端口号

# 会话配置
MAX_SESSIONS=10                    # 最大并发会话数
SESSION_TIMEOUT_SECONDS=3600       # 会话超时时间（秒）

# LLM 配置
OLLAMA_BASE_URL=http://127.0.0.1:11434
DEFAULT_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16
LLM_TEMPERATURE=0.4
ENABLE_LLM=true                    # 是否启用真实 LLM

# 按 Tutor 配置不同模型
TUTOR_1_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16
TUTOR_2_LLM_MODEL=llama3.1:8b-instruct-q4_K_M
```

## 🔄 进程管理

### 查看进程状态

```bash
# 查看 GPU Server 进程
ps aux | grep unified_server.py

# 查看进程树
pstree -p | grep python

# 查看 PID 文件
cat logs/server.pid
```

### 手动启动（不使用脚本）

```bash
# 使用 conda 环境
export PATH="/workspace/conda_envs/rag/bin:$PATH"
python unified_server.py

# 或者后台运行
nohup python unified_server.py > logs/server.log 2>&1 &
```

### 手动停止（不使用脚本）

```bash
# 通过 PID 停止
kill $(cat logs/server.pid)

# 通过进程名停止
pkill -f "python.*unified_server.py"

# 强制停止
pkill -9 -f "python.*unified_server.py"
```

## 📦 生产环境建议

在生产环境中，建议使用进程管理工具：

### 使用 systemd

创建服务文件 `/etc/systemd/system/gpu-server.service`：

```ini
[Unit]
Description=GPU Server
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/workspace/gpuserver
Environment="PATH=/workspace/conda_envs/rag/bin:/usr/bin"
ExecStart=/workspace/conda_envs/rag/bin/python unified_server.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

然后使用 systemd 管理：

```bash
sudo systemctl start gpu-server
sudo systemctl stop gpu-server
sudo systemctl restart gpu-server
sudo systemctl status gpu-server
sudo systemctl enable gpu-server  # 开机自启动
```

### 使用 Supervisor

安装 Supervisor：
```bash
pip install supervisor
```

配置文件 `supervisord.conf`：
```ini
[program:gpu-server]
command=/workspace/conda_envs/rag/bin/python unified_server.py
directory=/workspace/gpuserver
autostart=true
autorestart=true
stderr_logfile=/workspace/gpuserver/logs/supervisor_error.log
stdout_logfile=/workspace/gpuserver/logs/supervisor.log
```

使用 Supervisor 管理：
```bash
supervisorctl start gpu-server
supervisorctl stop gpu-server
supervisorctl restart gpu-server
supervisorctl status gpu-server
```

## 📚 相关文档

- [GPU Server README](README.md) - 项目主文档
- [Claude.md](../claude.md) - AI 助手上下文文档
- [LLM 模块文档](llm/README.md) - LLM 集成说明

---

**最后更新**: 2025-12-23
