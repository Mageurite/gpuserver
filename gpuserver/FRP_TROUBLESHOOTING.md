# frpc 连接问题诊断与解决方案

## 📋 问题总结

之前 frp 连不上的**根本原因**有以下几点：

### 1. 🔴 进程使用了错误的配置文件路径
**问题**：
- 旧的 frpc 进程在 `/workspace/gpuserver/temp/scripts` 目录启动
- 使用相对路径 `../frp_config/frpc.ini` 导致配置文件无法找到或使用了错误的配置
- 工作目录不对，导致配置路径解析失败

**影响**：
- frpc 虽然启动，但可能使用了错误的配置
- 无法正确连接到 frps 或代理配置不正确

### 2. 🔴 日志文件路径配置错误
**问题**：
- 配置文件中日志路径写的是 `/app/logs/frpc.log`（Docker 容器内路径）
- 但在宿主机直接运行时，该路径不存在或无权限
- 导致无法查看实时日志，难以排查问题

**修复**：
- 已将日志路径改为 `/workspace/gpuserver/logs/frpc.log`

### 3. 🔴 多个 frpc 进程冲突
**问题**：
- 多次手动启动导致有多个 frpc 实例同时运行
- 造成代理注册冲突："proxy already exists"
- 虽然日志显示 "start proxy success"，但实际连接不稳定

**典型日志**：
```
[W] [client/control.go:168] [gpu_management_api] start error: proxy [gpu_management_api] already exists
[W] [client/control.go:168] [gpu_websocket] start error: proxy [gpu_websocket] already exists
```

### 4. 🔴 连接断开未及时发现
**问题**：
- Dashboard 显示上次断开时间是 18:30:03
- 虽然 frpc 进程还在运行，但 frps 连接已断开
- 可能是网络抖动、配置错误或 frps 重启导致

## ✅ 解决方案

### 已创建的改进脚本

#### 1. `/workspace/gpuserver/start_frpc.sh` - 启动脚本
**功能特点**：
- ✅ 自动检测 frpc 可执行文件位置
- ✅ 验证配置文件存在且路径正确
- ✅ 检查配置参数（server_addr, token）
- ✅ **自动检测并清理旧进程**（避免重复启动）
- ✅ 支持 `--force` 参数自动清理重启
- ✅ 显示详细的启动信息和日志
- ✅ 保存 PID 文件便于管理

**使用方法**：
```bash
# 交互式启动（会询问是否停止旧进程）
cd /workspace/gpuserver
./start_frpc.sh

# 强制模式（自动清理旧进程）
./start_frpc.sh --force
```

#### 2. `/workspace/gpuserver/stop_frpc.sh` - 停止脚本
**功能特点**：
- ✅ 优雅停止（先 SIGTERM，再 SIGKILL）
- ✅ 清理 PID 文件
- ✅ 清理所有残留的 frpc 进程

**使用方法**：
```bash
cd /workspace/gpuserver
./stop_frpc.sh
```

#### 3. 更新了 `/workspace/gpuserver/start_all.sh`
- 优先使用新的 `start_frpc.sh`
- 使用 `--force` 参数避免交互

#### 4. 更新了 `/workspace/gpuserver/stop_all.sh`
- 优先使用新的 `stop_frpc.sh`
- 强制清理所有残留进程

### 配置文件修复

修改了 [frpc.ini](gpuserver/frpc.ini:15) 中的日志路径：
```ini
# 修改前
log_file = /app/logs/frpc.log

# 修改后
log_file = /workspace/gpuserver/logs/frpc.log
```

## 🚀 推荐使用方式

### 快速启动（推荐）
```bash
cd /workspace/gpuserver

# 方式 1: 只启动 frpc
./start_frpc.sh --force

# 方式 2: 启动 GPU Server + frpc
./start_all.sh
# 在提示时选择 Y 启动 FRP
```

### 查看状态
```bash
# 查看 frpc 进程
ps aux | grep frpc

# 查看实时日志
tail -f /workspace/gpuserver/logs/frpc.log

# 检查连接状态（访问 Dashboard API）
curl -u admin:xwl010907 http://51.161.130.234:7500/api/proxy/tcp

# 测试外部连接
curl http://51.161.130.234:19000/health
```

### 停止服务
```bash
# 只停止 frpc
./stop_frpc.sh

# 停止所有服务
./stop_all.sh
```

## 📊 验证清单

启动后请验证以下项目：

- [ ] frpc 进程正在运行（`ps aux | grep frpc`）
- [ ] 日志显示 "login to server success"
- [ ] 日志显示 "start proxy success"（两个代理）
- [ ] 外部 API 可访问（`curl http://51.161.130.234:19000/health`）
- [ ] Dashboard 显示代理状态为 "online"
- [ ] 无重复的 frpc 进程

## 🔍 故障排查

### 如果连接失败

1. **检查进程**：
```bash
ps aux | grep frpc
# 应该只有一个 frpc 进程
```

2. **查看日志**：
```bash
tail -50 /workspace/gpuserver/logs/frpc.log
# 查找 "login to server success" 和 "start proxy success"
```

3. **检查配置**：
```bash
cat /workspace/gpuserver/frpc.ini | grep -E "server_addr|token|remote_port"
```

4. **测试网络**：
```bash
# 测试 frps 端口
nc -zv 51.161.130.234 7000

# 测试代理端口
nc -zv 51.161.130.234 19000
nc -zv 51.161.130.234 19001
```

5. **重启 frpc**：
```bash
./stop_frpc.sh
./start_frpc.sh --force
```

### 如果看到 "proxy already exists" 错误

这说明有多个 frpc 进程在运行：
```bash
# 清理所有 frpc 进程
pkill -9 -f "frpc.*\.ini"

# 重新启动
./start_frpc.sh --force
```

## 📝 注意事项

1. **始终使用脚本启动**：避免直接运行 `frpc` 命令，使用 `start_frpc.sh` 可以自动处理冲突
2. **使用 --force 参数**：在自动化场景（如 start_all.sh）中使用 `--force` 避免交互
3. **检查日志**：定期查看日志文件确保连接稳定
4. **监控连接状态**：可以通过 Dashboard API 实时监控代理状态

## 🎯 当前配置信息

| 项目 | 值 | 说明 |
|------|-----|------|
| frps 服务器 | 51.161.130.234:7000 | 控制端口 |
| 认证 Token | xwl010907 | 必须与 frps 一致 |
| API 代理端口 | 19000 | 本地 9000 → 远程 19000 |
| WebSocket 代理端口 | 19001 | 本地 9000 → 远程 19001 |
| Dashboard | http://51.161.130.234:7500 | 用户: admin, 密码: xwl010907 |

---

**最后更新**: 2025-12-24
**状态**: ✅ 已解决并测试通过
