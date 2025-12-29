# GPU Server 启动脚本使用指南

## 📋 脚本列表

| 脚本 | 功能 | 说明 |
|------|------|------|
| `start_server.sh` | 启动服务器 | 启动 GPU Server WebSocket 服务 |
| `stop_server.sh` | 停止服务器 | 停止运行中的 GPU Server |
| `status_server.sh` | 查看状态 | 查看服务器运行状态和日志 |

---

## 🚀 快速开始

### 1. 启动服务器

```bash
cd /workspace/gpuserver
./start_server.sh
```

**输出示例**：
```
[INFO] GPU Server 启动脚本
================================
[INFO] 检查 Python 环境...
[SUCCESS] 使用 conda rag 环境: /workspace/conda_envs/rag/bin/python
[INFO] Python 版本: Python 3.12.3
[INFO] 设置 PYTHONPATH: /workspace/gpuserver
[INFO] 检查必需的文件...
[SUCCESS] 所有必需文件存在
[INFO] 检查端口 19001 是否被占用...
[SUCCESS] 端口 19001 可用
[INFO] 日志文件: /workspace/gpuserver/logs/websocket_server.log
[INFO] 启动 GPU Server...
================================
[INFO] 后台运行模式
[SUCCESS] GPU Server 已启动 (PID: 123456)
[INFO] 日志文件: /workspace/gpuserver/logs/websocket_server.log
[INFO] 等待服务器启动...
[SUCCESS] GPU Server 运行正常
[INFO] 测试健康检查接口...
[SUCCESS] 健康检查通过
{
  "status": "healthy",
  "service": "GPU Server WebSocket API",
  "active_connections": 0
}

================================
[SUCCESS] GPU Server 启动成功！

📍 WebSocket 端点:
   - ws://localhost:19001/ws/{connection_id}
   - ws://localhost:19001/ws/ws/{connection_id}

📊 管理命令:
   - 查看日志: tail -f /workspace/gpuserver/logs/websocket_server.log
   - 停止服务: ./stop_server.sh
   - 查看状态: ps -p 123456
```

### 2. 前台运行模式（用于调试）

```bash
./start_server.sh --foreground
# 或
./start_server.sh -f
```

**说明**：前台运行模式会直接显示日志输出，按 `Ctrl+C` 停止服务器。

---

## 🛑 停止服务器

```bash
./stop_server.sh
```

**输出示例**：
```
[INFO] GPU Server 停止脚本
================================
[INFO] 从 PID 文件读取: 123456
[INFO] 停止进程 123456...
[SUCCESS] 进程已停止
[INFO] 检查端口 19001...
[SUCCESS] 端口 19001 未被占用
[INFO] 清理其他相关进程...

================================
[SUCCESS] GPU Server 已停止
```

---

## 📊 查看服务器状态

```bash
./status_server.sh
```

**输出示例**：
```
================================
[INFO] GPU Server 状态
================================

[INFO] PID 文件: 123456
[SUCCESS] 进程运行中 (PID: 123456)

[INFO] 进程详情:
    PID   PPID CMD                         %CPU %MEM     ELAPSED
 123456      1 /workspace/conda_envs/ra...  0.5  2.3    00:05:23

[INFO] 端口状态 (19001):
[SUCCESS] 端口 19001 正在监听

COMMAND     PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
python    123456 root    8u  IPv4 123456      0t0  TCP *:19001 (LISTEN)

[INFO] 健康检查:
[SUCCESS] 健康检查通过
{
  "status": "healthy",
  "service": "GPU Server WebSocket API",
  "active_connections": 2
}

[INFO] 最近日志 (最后 20 行):
================================
INFO:     Started server process [123456]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:19001
...
================================

[INFO] 完整日志: /workspace/gpuserver/logs/websocket_server.log

[INFO] 管理命令:
  启动服务: ./start_server.sh
  停止服务: ./stop_server.sh
  查看日志: tail -f /workspace/gpuserver/logs/websocket_server.log
  重启服务: ./stop_server.sh && ./start_server.sh
```

---

## 📝 查看日志

### 实时查看日志

```bash
tail -f logs/websocket_server.log
```

### 查看最近的日志

```bash
tail -50 logs/websocket_server.log
```

### 搜索日志

```bash
# 搜索错误
grep -i error logs/websocket_server.log

# 搜索特定 session
grep "session_id=abc123" logs/websocket_server.log

# 搜索 WebSocket 连接
grep "WebSocket connected" logs/websocket_server.log
```

---

## 🔄 重启服务器

```bash
./stop_server.sh && ./start_server.sh
```

或者创建一个重启脚本：

```bash
# 快速重启
./stop_server.sh && sleep 2 && ./start_server.sh
```

---

## 🔧 脚本功能详解

### start_server.sh

**功能**：
- ✅ 自动检测 Python 环境（优先使用 conda 环境）
- ✅ 检查必需文件是否存在
- ✅ 检查端口是否被占用
- ✅ 设置 PYTHONPATH 环境变量
- ✅ 后台启动服务器
- ✅ 保存 PID 到文件
- ✅ 测试健康检查接口
- ✅ 显示管理命令

**参数**：
- `--foreground` 或 `-f`：前台运行模式

**环境变量**：
- `PYTHONPATH`：自动设置为 `/workspace/gpuserver`

**日志文件**：
- 位置：`/workspace/gpuserver/logs/websocket_server.log`
- 自动创建日志目录

**PID 文件**：
- 位置：`/workspace/gpuserver/websocket_server.pid`
- 用于停止和状态检查

### stop_server.sh

**功能**：
- ✅ 从 PID 文件读取进程 ID
- ✅ 优雅停止进程（SIGTERM）
- ✅ 如果进程未响应，强制停止（SIGKILL）
- ✅ 检查并释放端口
- ✅ 清理相关进程
- ✅ 删除 PID 文件

**停止策略**：
1. 尝试优雅停止（等待 10 秒）
2. 如果失败，强制停止
3. 清理端口占用
4. 清理其他相关进程

### status_server.sh

**功能**：
- ✅ 显示进程状态（PID、CPU、内存、运行时间）
- ✅ 显示端口监听状态
- ✅ 测试健康检查接口
- ✅ 显示最近的日志（最后 20 行）
- ✅ 显示管理命令

**信息展示**：
- 进程信息（PID、PPID、CMD、CPU、内存、运行时间）
- 端口监听状态
- 健康检查结果
- 最近日志

---

## 🐛 故障排查

### 问题 1: 启动失败 - 端口被占用

**症状**：
```
[WARNING] 端口 19001 已被占用
```

**解决方案**：
```bash
# 方案 1: 停止现有进程
./stop_server.sh

# 方案 2: 手动释放端口
lsof -ti:19001 | xargs kill -9

# 方案 3: 启动时自动处理
# 脚本会提示是否停止现有进程
```

### 问题 2: 启动失败 - Python 环境问题

**症状**：
```
[ERROR] 未找到 Python 环境！
```

**解决方案**：
```bash
# 检查 Python 环境
which python3
python3 --version

# 检查 conda 环境
ls -la /workspace/conda_envs/

# 手动指定 Python 路径（修改脚本）
PYTHON_BIN="/path/to/python"
```

### 问题 3: 启动失败 - 缺少依赖

**症状**：
```
ModuleNotFoundError: No module named 'xxx'
```

**解决方案**：
```bash
# 使用正确的 conda 环境
/workspace/conda_envs/rag/bin/python -m pip install xxx

# 或者安装所有依赖
/workspace/conda_envs/rag/bin/python -m pip install -r requirements.txt
```

### 问题 4: 服务器启动但无法连接

**症状**：
```
[ERROR] 健康检查失败
```

**解决方案**：
```bash
# 1. 查看日志
tail -50 logs/websocket_server.log

# 2. 检查进程状态
./status_server.sh

# 3. 检查端口
netstat -tlnp | grep 19001

# 4. 测试连接
curl http://localhost:19001/health
```

### 问题 5: 进程意外停止

**症状**：
```
[ERROR] 进程不存在 (PID: 123456)
```

**解决方案**：
```bash
# 1. 查看日志找出原因
tail -100 logs/websocket_server.log

# 2. 清理并重启
./stop_server.sh
./start_server.sh

# 3. 前台运行查看详细错误
./start_server.sh --foreground
```

---

## 📚 相关文档

- `FINAL_MODIFICATIONS_CHECKLIST.md` - 修改检查清单
- `GPU_SERVER_MODIFICATIONS_SUMMARY.md` - 详细修改说明
- `TESTING_GUIDE.md` - 完整测试指南
- `WEBSOCKET_TEST_REPORT.md` - WebSocket 测试报告

---

## 🎯 常用命令速查

```bash
# 启动服务器
./start_server.sh

# 前台运行（调试）
./start_server.sh -f

# 停止服务器
./stop_server.sh

# 查看状态
./status_server.sh

# 重启服务器
./stop_server.sh && ./start_server.sh

# 查看实时日志
tail -f logs/websocket_server.log

# 测试健康检查
curl http://localhost:19001/health

# 测试 WebSocket 连接
python3 test_websocket_client.py

# 查看进程
ps aux | grep websocket_server

# 查看端口
lsof -i:19001
```

---

## ⚙️ 配置说明

### 端口配置

默认端口：`19001`

修改端口：编辑 `config.py`
```python
websocket_port = 19001  # 修改为其他端口
```

### 日志配置

日志位置：`logs/websocket_server.log`

修改日志级别：编辑 `api/websocket_server.py`
```python
logging.basicConfig(
    level=logging.INFO,  # 修改为 DEBUG, WARNING, ERROR
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Python 环境配置

优先级顺序：
1. `/workspace/conda_envs/rag/bin/python`
2. `/workspace/conda_envs/mt/bin/python`
3. `python3` (系统 Python)

修改优先级：编辑 `start_server.sh`

---

## 🔐 安全注意事项

1. **端口访问**：确保端口 19001 只对可信网络开放
2. **Token 验证**：所有 WebSocket 连接都需要有效的 token
3. **日志权限**：日志文件可能包含敏感信息，注意权限设置
4. **进程权限**：建议使用非 root 用户运行服务器

---

## 📞 支持

如有问题，请：
1. 查看日志：`tail -f logs/websocket_server.log`
2. 查看状态：`./status_server.sh`
3. 参考故障排查部分
4. 查看相关文档

---

**创建日期**: 2025-12-29
**版本**: 1.0.0
