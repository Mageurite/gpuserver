# GPU Server 快速参考指南

## 🚀 常用命令

### 服务管理

```bash
# 启动服务
./start.sh

# 停止服务
./stop.sh

# 重启服务
./restart.sh

# 查看状态
./status.sh

# 测试连接
./test_webserver_connection.sh
```

## 📊 服务状态检查

### 快速检查

```bash
# 检查服务是否运行
pgrep -f "python.*unified_server.py"

# 健康检查
curl http://localhost:9000/health

# 查看日志
tail -f logs/server.log
```

### 详细检查

```bash
# 查看完整状态
./status.sh

# 包含以下信息：
# - 进程状态（PID、运行时长、内存/CPU）
# - PID 文件状态
# - 端口占用情况
# - 健康检查结果
# - 日志文件信息
# - 配置文件内容
# - 访问地址
```

## 🔌 连接测试

### 测试 GPU Server 与 Web Server 连接

```bash
./test_webserver_connection.sh
```

**测试内容：**
1. GPU Server 健康检查
2. Web Server 健康检查
3. ENGINE_URL 配置验证
4. 会话创建测试
5. 会话查询测试
6. WebSocket 连接测试（可选）
7. 会话清理测试
8. 网络连通性总结

### 手动测试 API

```bash
# 健康检查
curl http://localhost:9000/health

# 创建会话
curl -X POST http://localhost:9000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 123}'

# 查询会话（替换 SESSION_ID）
curl http://localhost:9000/v1/sessions/SESSION_ID

# 删除会话
curl -X DELETE http://localhost:9000/v1/sessions/SESSION_ID
```

## 📝 日志管理

```bash
# 实时查看日志
tail -f logs/server.log

# 查看最近 50 行
tail -n 50 logs/server.log

# 查看完整日志
cat logs/server.log

# 搜索错误
grep -i error logs/server.log

# 清空日志（谨慎使用）
> logs/server.log
```

## 🔧 配置管理

### 查看配置

```bash
# 查看环境变量
cat .env

# 查看特定配置
grep "MANAGEMENT_API_PORT" .env
grep "ENABLE_LLM" .env
```

### 修改配置

```bash
# 编辑配置
vim .env

# 修改后需要重启服务
./restart.sh
```

### 关键配置项

```bash
# 服务器配置
MANAGEMENT_API_HOST=0.0.0.0
MANAGEMENT_API_PORT=9000

# 会话配置
MAX_SESSIONS=10
SESSION_TIMEOUT_SECONDS=3600

# LLM 配置
OLLAMA_BASE_URL=http://127.0.0.1:11434
DEFAULT_LLM_MODEL=mistral-nemo:12b-instruct-2407-fp16
ENABLE_LLM=true
```

## 🐛 故障排查

### 服务无法启动

```bash
# 1. 查看日志
cat logs/server.log

# 2. 检查端口占用
lsof -i :9000

# 3. 检查进程
ps aux | grep unified_server.py

# 4. 强制清理并重启
pkill -9 -f "python.*unified_server.py"
./start.sh
```

### 服务无法停止

```bash
# 1. 使用停止脚本
./stop.sh

# 2. 查找进程
pgrep -af "unified_server.py"

# 3. 强制停止
pkill -9 -f "python.*unified_server.py"

# 4. 清理 PID 文件
rm -f logs/server.pid
```

### 端口被占用

```bash
# 查看占用端口的进程
lsof -i :9000

# 杀死占用端口的进程
kill -9 $(lsof -t -i:9000)

# 或修改配置使用其他端口
vim .env  # 修改 MANAGEMENT_API_PORT
./restart.sh
```

### Web Server 无法连接

```bash
# 1. 运行连接测试
./test_webserver_connection.sh

# 2. 检查配置
cat /workspace/virtual_tutor/app_backend/.env | grep ENGINE_URL

# 3. 应该是：ENGINE_URL=http://localhost:9000

# 4. 重启 Web Server
cd /workspace/virtual_tutor/app_backend
pkill -f 'uvicorn app.main:app'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### LLM 不工作

```bash
# 1. 检查配置
grep "ENABLE_LLM" .env  # 应该是 true

# 2. 检查 Ollama 是否运行
curl http://127.0.0.1:11434/api/tags

# 3. 检查模型是否安装
ollama list

# 4. 安装模型（如果需要）
ollama pull mistral-nemo:12b-instruct-2407-fp16

# 5. 重启服务
./restart.sh
```

## 📍 访问地址

```bash
# 管理 API
http://localhost:9000/mgmt/v1/sessions

# 管理 API（兼容模式）
http://localhost:9000/v1/sessions

# WebSocket
ws://localhost:9000/ws/ws/{session_id}?token={token}

# API 文档
http://localhost:9000/docs

# 健康检查
http://localhost:9000/health

# 根路径信息
http://localhost:9000/
```

## 🔐 安全提示

1. **生产环境**：修改 `MANAGEMENT_API_HOST` 为内网 IP，不要暴露到公网
2. **防火墙**：限制 9000 端口只允许 Web Server 访问
3. **环境变量**：不要提交 `.env` 文件到 Git
4. **日志文件**：定期清理，避免占用过多磁盘

## 📦 文件说明

```
gpuserver/
├── start.sh                          # 启动脚本 ⭐
├── stop.sh                           # 停止脚本 ⭐
├── restart.sh                        # 重启脚本 ⭐
├── status.sh                         # 状态查询脚本 ⭐
├── test_webserver_connection.sh     # 连接测试脚本 ⭐
├── unified_server.py                 # 主服务程序
├── .env                              # 配置文件（需创建）
├── .env.example                      # 配置模板
├── logs/                             # 日志目录
│   ├── server.log                   # 服务日志
│   └── server.pid                   # 进程 PID
├── README.md                         # 详细文档
├── SCRIPTS_GUIDE.md                 # 脚本使用指南
└── 本文件                            # 快速参考
```

## 🎯 最佳实践

### 开发环境

```bash
# 1. 首次启动
cp .env.example .env
vim .env  # 根据需要修改
./start.sh

# 2. 开发过程中
tail -f logs/server.log  # 终端1：查看日志
./status.sh              # 终端2：检查状态

# 3. 修改代码后
./restart.sh             # 重启服务

# 4. 测试连接
./test_webserver_connection.sh
```

### 生产环境

```bash
# 1. 配置生产参数
vim .env
# - 设置合适的 MAX_SESSIONS
# - 设置合适的 SESSION_TIMEOUT_SECONDS
# - 启用真实 LLM: ENABLE_LLM=true

# 2. 使用进程管理工具（推荐 systemd 或 supervisor）
# 见 SCRIPTS_GUIDE.md

# 3. 设置日志轮转
# 避免日志文件过大

# 4. 监控
# - 定期运行 ./status.sh
# - 监控端口 9000
# - 监控磁盘空间（日志）
```

## 📞 获取帮助

- 详细文档：[README.md](README.md)
- 脚本指南：[SCRIPTS_GUIDE.md](SCRIPTS_GUIDE.md)
- 上下文文档：[../claude.md](../claude.md)
- LLM 文档：[llm/README.md](llm/README.md)

---

**最后更新**: 2025-12-23
