# GPU Server 快速启动指南

## 🚀 一键启动（推荐）

```bash
cd /workspace/gpuserver
./start_all.sh
```

启动时会询问是否启用 FRP，选择 `Y` 即可。

## 📋 分步启动

### 1. 只启动 GPU Server
```bash
cd /workspace/gpuserver
python3 unified_server.py &
```

### 2. 只启动 FRP 内网穿透
```bash
cd /workspace/gpuserver
./start_frpc.sh --force
```

### 3. 启动全部服务
```bash
./start_all.sh
```

## 🛑 停止服务

```bash
# 停止所有服务（GPU Server + FRP）
./stop_all.sh

# 只停止 GPU Server（会询问是否停止 FRP）
./stop.sh

# 只停止 FRP
./stop_frpc.sh
```

## 🔄 重启服务

```bash
# 重启所有服务（推荐）
./restart_all.sh

# 只重启 GPU Server
./restart.sh
```

## 🔍 查看状态

```bash
# 查看详细状态（包括 GPU Server 和 FRP）⭐
./status.sh

# 查看进程
ps aux | grep -E "unified_server|frpc"

# 查看 GPU Server 日志
tail -f logs/unified_server.log

# 查看 FRP 日志
tail -f logs/frpc.log

# 测试本地连接
curl http://localhost:9000/health

# 测试外网连接（通过 FRP）
curl http://51.161.130.234:19000/health
```

## 📊 服务地址

### 本地访问
- **API**: http://localhost:9000
- **WebSocket**: ws://localhost:9000/ws/ws/{session_id}
- **文档**: http://localhost:9000/docs

### 外网访问（通过 FRP）
- **API**: http://51.161.130.234:19000
- **WebSocket**: ws://51.161.130.234:19001/ws/ws/{session_id}
- **FRP Dashboard**: http://51.161.130.234:7500
  - 用户名: `admin`
  - 密码: `xwl010907`

## ⚠️ 常见问题

### FRP 连接失败？
详见 [FRP_TROUBLESHOOTING.md](FRP_TROUBLESHOOTING.md)

### GPU Server 启动失败？
```bash
# 查看详细日志
tail -100 logs/unified_server.log

# 检查端口占用
lsof -i :9000

# 如果端口被占用，停止所有服务
./stop_all.sh
```

### 如何重启服务？
```bash
# 重启所有服务（推荐）
./restart_all.sh

# 只重启 GPU Server
./restart.sh
```

### 如何查看完整状态？
```bash
# 查看详细的服务状态（包括 GPU Server、FRP、端口、日志等）
./status.sh
```

---

💡 **提示**: 首次启动建议使用 `./start_all.sh`，它会自动处理环境检查和配置。
