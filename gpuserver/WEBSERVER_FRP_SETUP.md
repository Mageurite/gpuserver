# Web Server FRP 配置完整指南

## 📋 概述

本指南详细说明如何在 Web Server 上配置和运行 FRP 服务端(frps)，用于接收 GPU Server 的反向隧道连接。

---

## 🎯 架构说明

```
┌──────────────┐         FRP 隧道          ┌──────────────┐
│  GPU Server  │ ────────────────────────> │  Web Server  │
│              │    (主动建立连接)          │              │
│ frpc:客户端  │                           │ frps:服务端  │
│              │                           │              │
│ Port 9000    │ ─────[隧道]────────────> │ Port 19000   │
│ Port 9001    │ ─────[隧道]────────────> │ Port 19001   │
└──────────────┘                           └──────────────┘
      内网/无公网IP                              公网服务器
```

**关键点：**
- GPU Server **主动连接** Web Server
- Web Server 需要有**可访问的IP或域名**
- 不需要 GPU Server 有公网 IP

---

## 📦 方案一：Docker 部署（推荐）

### 1. 下载 FRP

```bash
# 在 Web Server 上执行
cd ~
wget https://github.com/fatedier/frp/releases/download/v0.66.0/frp_0.66.0_linux_amd64.tar.gz
tar -xzf frp_0.66.0_linux_amd64.tar.gz
cd frp_0.66.0_linux_amd64
```

### 2. 创建配置文件

创建 `frps.toml`：

```toml
# FRP Server 配置文件
# 部署在 Web Server 上

# 服务监听端口（GPU Server 连接这个端口）
bindPort = 7000

# 认证 Token（必须与 GPU Server 的 frpc.toml 一致）
auth.token = "xwl010907"

# Dashboard 配置（可选，用于监控）
webServer.addr = "0.0.0.0"
webServer.port = 7500
webServer.user = "admin"
webServer.password = "VirtualTutor2024!"

# 日志配置
log.to = "/var/log/frps.log"
log.level = "info"
log.maxDays = 7

# 允许的端口范围
allowPorts = [
  { start = 19000, end = 19010 }
]
```

### 3. 创建 Docker Compose 文件

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  frps:
    image: snowdreamtech/frps:latest
    container_name: frps
    restart: always
    network_mode: host
    volumes:
      - ./frps.toml:/etc/frp/frps.toml:ro
      - ./logs:/var/log
    command: -c /etc/frp/frps.toml
```

### 4. 启动服务

```bash
# 创建日志目录
mkdir -p logs

# 启动 FRP Server
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 5. 验证服务

```bash
# 检查端口监听
netstat -tlnp | grep 7000
netstat -tlnp | grep 7500

# 预期输出：
# tcp  0  0.0.0.0:7000  0.0.0.0:*  LISTEN  xxx/frps
# tcp  0  0.0.0.0:7500  0.0.0.0:*  LISTEN  xxx/frps

# 访问 Dashboard（在浏览器中）
# http://YOUR_WEB_SERVER_IP:7500
# 用户名: admin
# 密码: VirtualTutor2024!
```

---

## 📦 方案二：直接运行（不用 Docker）

### 1. 下载和安装

```bash
# 在 Web Server 上执行
cd /opt
wget https://github.com/fatedier/frp/releases/download/v0.66.0/frp_0.66.0_linux_amd64.tar.gz
tar -xzf frp_0.66.0_linux_amd64.tar.gz
mv frp_0.66.0_linux_amd64 frp
cd frp
```

### 2. 配置 frps.toml

```bash
cat > frps.toml << 'EOF'
# FRP Server 配置
bindPort = 7000
auth.token = "xwl010907"

# Dashboard
webServer.addr = "0.0.0.0"
webServer.port = 7500
webServer.user = "admin"
webServer.password = "VirtualTutor2024!"

# 日志
log.to = "/var/log/frps.log"
log.level = "info"
log.maxDays = 7

# 允许端口
allowPorts = [
  { start = 19000, end = 19010 }
]
EOF
```

### 3. 创建 systemd 服务

```bash
cat > /etc/systemd/system/frps.service << 'EOF'
[Unit]
Description=FRP Server Service
After=network.target

[Service]
Type=simple
User=root
Restart=on-failure
RestartSec=5s
ExecStart=/opt/frp/frps -c /opt/frp/frps.toml
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
```

### 4. 启动服务

```bash
# 重载 systemd
systemctl daemon-reload

# 启动 frps
systemctl start frps

# 设置开机自启
systemctl enable frps

# 查看状态
systemctl status frps

# 查看日志
journalctl -u frps -f
```

---

## 🔧 GPU Server 端配置

配置完 Web Server 后，在 GPU Server 上配置客户端：

### 修改 frpc.toml

在 GPU Server 上创建或修改 `/workspace/gpuserver/frpc.toml`：

```toml
# FRP Client 配置
# 连接到 Web Server

# Web Server 地址（修改为你的实际地址）
serverAddr = "51.161.130.234"
serverPort = 7000

# 认证 Token（必须与 frps 一致）
auth.token = "xwl010907"

# 日志
log.to = "/workspace/gpuserver/logs/frpc.log"
log.level = "info"
log.maxDays = 7

# 心跳配置
transport.heartbeatInterval = 30
transport.heartbeatTimeout = 90

# TCP 多路复用
transport.tcpMux = true

# Management API 端口转发
[[proxies]]
name = "gpu_management_api"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9000
remotePort = 19000

# WebSocket 端口转发
[[proxies]]
name = "gpu_websocket"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9001
remotePort = 19001
```

### 启动 GPU Server 端

```bash
cd /workspace/gpuserver

# 方法1：直接运行
./frpc -c frpc.toml

# 方法2：后台运行
nohup ./frpc -c frpc.toml > logs/frpc.log 2>&1 &

# 方法3：使用 screen（推荐）
screen -dmS frpc ./frpc -c frpc.toml
```

---

## 🔍 测试连接

### 在 Web Server 上测试

```bash
# 1. 检查 frps 是否运行
ps aux | grep frps
netstat -tlnp | grep 7000

# 2. 等待 GPU Server 连接（查看 Dashboard）
# 浏览器访问: http://YOUR_IP:7500

# 3. 检查转发端口是否已监听
netstat -tlnp | grep 19000
netstat -tlnp | grep 19001

# 4. 测试 API 连接
curl http://localhost:19000/mgmt/health

# 5. 测试 WebSocket（需要 wscat）
npm install -g wscat
wscat -c ws://localhost:19001/ws
```

### 在 GPU Server 上检查

```bash
# 查看 frpc 日志
tail -f /workspace/gpuserver/logs/frpc.log

# 预期看到：
# [I] [service.go:xxx] login to server success
# [I] [proxy_manager.go:xxx] proxy added: [gpu_management_api]
# [I] [proxy_manager.go:xxx] proxy added: [gpu_websocket]
```

---

## 🔥 防火墙配置

### Web Server 防火墙规则

```bash
# 开放 FRP 服务端口
ufw allow 7000/tcp comment 'FRP Server'

# 开放 Dashboard 端口（可选）
ufw allow 7500/tcp comment 'FRP Dashboard'

# 开放转发端口（如果需要外部访问）
ufw allow 19000/tcp comment 'GPU Management API'
ufw allow 19001/tcp comment 'GPU WebSocket'

# 重载防火墙
ufw reload

# 查看规则
ufw status numbered
```

### 云服务器安全组

如果使用云服务器（AWS/阿里云/腾讯云等），需要在控制台配置安全组：

- **入站规则**：
  - TCP 7000（FRP 服务端口）
  - TCP 7500（Dashboard，可选）
  - TCP 19000-19001（转发端口，如需外部访问）

---

## 🐛 故障排查

### 问题 1：GPU Server 无法连接

**症状：** frpc 日志显示 "dial tcp: connect: connection refused"

**解决方案：**
```bash
# 1. 检查 Web Server 的 frps 是否运行
ps aux | grep frps
netstat -tlnp | grep 7000

# 2. 检查防火墙
ufw status
# 或
iptables -L -n | grep 7000

# 3. 检查 token 是否一致
# Web Server: cat frps.toml | grep token
# GPU Server: cat frpc.toml | grep token
```

### 问题 2：端口冲突

**症状：** "bind: address already in use"

**解决方案：**
```bash
# 查找占用端口的进程
lsof -i :19000
netstat -tlnp | grep 19000

# 杀掉占用进程
kill <PID>

# 或修改配置使用其他端口
```

### 问题 3：连接频繁断开

**解决方案：**
```toml
# 在 frpc.toml 中调整心跳参数
transport.heartbeatInterval = 10  # 减小心跳间隔
transport.heartbeatTimeout = 30   # 减小超时时间
```

---

## 📊 监控和维护

### 查看连接状态

访问 Dashboard: `http://YOUR_WEB_SERVER_IP:7500`

显示：
- 在线的客户端
- 活动的代理
- 流量统计

### 日志管理

```bash
# 查看实时日志
tail -f /var/log/frps.log

# 日志轮转配置（/etc/logrotate.d/frps）
/var/log/frps.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

### 性能监控

```bash
# CPU 和内存使用
top -p $(pgrep frps)

# 网络流量
iftop -i eth0

# 连接数
netstat -an | grep :7000 | wc -l
```

---

## ✅ 完整部署检查清单

### Web Server 端：
- [ ] 安装 FRP 服务端
- [ ] 配置 frps.toml
- [ ] 启动 frps 服务
- [ ] 配置防火墙规则
- [ ] 验证端口监听（7000, 7500）
- [ ] 访问 Dashboard 确认运行

### GPU Server 端：
- [ ] 配置 frpc.toml
- [ ] 设置正确的 serverAddr
- [ ] 确认 token 一致
- [ ] 启动 frpc 客户端
- [ ] 查看日志确认连接成功

### 测试验证：
- [ ] Dashboard 显示客户端在线
- [ ] 端口 19000, 19001 已监听
- [ ] API 测试成功
- [ ] WebSocket 测试成功

---

## 🔗 相关资源

- FRP 官方文档: https://github.com/fatedier/frp
- FRP 中文文档: https://gofrp.org/zh-cn/
- Docker 镜像: https://hub.docker.com/r/snowdreamtech/frps

---

## 💡 高级配置

### 启用 HTTPS

```toml
# 在 frps.toml 中
webServer.tls.certFile = "/path/to/cert.pem"
webServer.tls.keyFile = "/path/to/key.pem"
```

### 限制带宽

```toml
# 在 frps.toml 中
transport.maxPoolCount = 50
```

### 配置多个客户端

```toml
# 每个客户端使用不同的 token 或配置不同的端口范围
allowPorts = [
  { start = 19000, end = 19010 },  # GPU Server 1
  { start = 19100, end = 19110 }   # GPU Server 2
]
```

完成配置后，你的 Web Server 就可以接收来自 GPU Server 的 FRP 连接了！
