# 从 FRP 迁移到 SSH 反向隧道指南

## 📋 概述

本指南帮助你从 FRP（Fast Reverse Proxy）迁移到 SSH 反向隧道，实现 GPU Server 到 Web Server 的连接。

### 为什么使用 SSH 反向隧道？

**优势：**
- ✅ 无需额外的 FRP 服务器和客户端
- ✅ 使用标准 SSH 协议，更安全
- ✅ 配置简单，易于调试
- ✅ 支持自动重连（使用 autossh）
- ✅ 无需额外端口（只需 SSH 端口）

**对比 FRP：**
| 特性 | SSH 隧道 | FRP |
|------|---------|-----|
| 依赖 | SSH (系统自带) | 需要 frp 二进制文件 |
| 安全性 | SSH 加密 + 密钥认证 | Token 认证 |
| 配置复杂度 | 简单 | 中等 |
| 维护成本 | 低 | 中等（需维护 frps 服务器） |
| 自动重连 | 支持 (autossh) | 支持 |
| UDP 支持 | 不支持 | 支持 |

---

## 📦 迁移步骤

### 1. 准备工作

#### 在 GPU Server 上：

```bash
cd /workspace/gpuserver

# 检查是否安装了 SSH 客户端
ssh -V

# 安装 autossh（推荐，用于自动重连）
apt-get update && apt-get install -y autossh

# 生成 SSH 密钥（如果还没有）
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
```

#### 在 Web Server 上：

```bash
# 添加 GPU Server 的公钥到授权列表
# 在 GPU Server 上执行：
cat ~/.ssh/id_rsa.pub

# 复制输出内容，然后在 Web Server 上执行：
mkdir -p ~/.ssh
echo "粘贴公钥内容" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh

# 测试 SSH 连接（在 GPU Server 上）
ssh root@51.161.130.234 "echo 'SSH 连接成功'"
```

### 2. 配置 SSH 反向隧道

编辑配置文件：

```bash
cd /workspace/gpuserver
nano tunnel_config.sh
```

修改以下配置项：

```bash
# Web Server 配置
WEBSERVER_HOST="51.161.130.234"  # 修改为你的 Web Server IP
WEBSERVER_SSH_PORT="22"          # SSH 端口
WEBSERVER_USER="root"            # SSH 用户名

# SSH 密钥路径
SSH_KEY_PATH="/root/.ssh/id_rsa"

# 端口映射（保持与 FRP 配置一致）
LOCAL_MGMT_PORT="9000"           # GPU Server Management API 端口
REMOTE_MGMT_PORT="19000"         # Web Server 暴露的 API 端口
LOCAL_WS_PORT="9001"             # GPU Server WebSocket 端口
REMOTE_WS_PORT="19001"           # Web Server 暴露的 WebSocket 端口
```

### 3. 给脚本添加执行权限

```bash
cd /workspace/gpuserver
chmod +x start_tunnel.sh
chmod +x stop_tunnel.sh
chmod +x status_tunnel.sh
chmod +x tunnel_config.sh
```

### 4. 启动 SSH 反向隧道

```bash
cd /workspace/gpuserver
./start_tunnel.sh
```

输出示例：
```
[INFO] SSH 反向隧道启动脚本
========================================
[SUCCESS] 使用 SSH 密钥: /root/.ssh/id_rsa
[INFO] 测试 SSH 连接...
SSH 连接测试成功
[SUCCESS] SSH 连接测试成功
[INFO] 启动 SSH 反向隧道...
----------------------------------------
Management API: 127.0.0.1:9000 -> 51.161.130.234:19000
WebSocket:      127.0.0.1:9001 -> 51.161.130.234:19001
----------------------------------------
[SUCCESS] SSH 反向隧道已启动 (PID: 12345)
```

### 5. 验证隧道状态

```bash
./status_tunnel.sh
```

### 6. 在 Web Server 上验证

在 Web Server 上测试端口是否监听：

```bash
# 检查端口
netstat -tlnp | grep 19000
netstat -tlnp | grep 19001

# 测试 API 连接
curl http://localhost:19000/mgmt/health

# 测试 WebSocket（需要 wscat）
# npm install -g wscat
wscat -c ws://localhost:19001/ws/chat
```

### 7. 停止旧的 FRP 服务

确认 SSH 隧道工作正常后，停止 FRP：

```bash
# 停止 FRP 客户端
screen -X -S frpc_bg quit

# 或者查找并杀掉 frpc 进程
ps aux | grep frpc
kill <PID>
```

---

## 🔧 管理命令

### 启动隧道
```bash
cd /workspace/gpuserver
./start_tunnel.sh
```

### 停止隧道
```bash
./stop_tunnel.sh
```

### 查看状态
```bash
./status_tunnel.sh
```

### 查看日志
```bash
tail -f /workspace/gpuserver/logs/ssh_tunnel.log
```

### 重启隧道
```bash
./stop_tunnel.sh && ./start_tunnel.sh
```

---

## 🚀 开机自动启动（可选）

### 方法 1：使用 systemd 服务

```bash
# 复制服务文件
sudo cp /workspace/gpuserver/ssh-tunnel.service /etc/systemd/system/

# 重载 systemd
sudo systemctl daemon-reload

# 启用开机自动启动
sudo systemctl enable ssh-tunnel

# 启动服务
sudo systemctl start ssh-tunnel

# 查看状态
sudo systemctl status ssh-tunnel

# 查看日志
sudo journalctl -u ssh-tunnel -f
```

### 方法 2：使用 crontab

```bash
# 编辑 crontab
crontab -e

# 添加以下行（开机启动）
@reboot /workspace/gpuserver/start_tunnel.sh

# 或者每 5 分钟检查一次（确保隧道不中断）
*/5 * * * * /workspace/gpuserver/status_tunnel.sh || /workspace/gpuserver/start_tunnel.sh
```

---

## 🐛 故障排查

### 问题 1：SSH 连接失败

**错误信息：**
```
Permission denied (publickey,password).
```

**解决方案：**
```bash
# 1. 检查 SSH 密钥是否正确配置
ssh -i ~/.ssh/id_rsa root@51.161.130.234

# 2. 如果密钥不work，尝试使用密码认证
# 在 tunnel_config.sh 中注释掉 SSH_KEY_PATH
# SSH_KEY_PATH=""

# 3. 检查 Web Server 的 SSH 配置
# 在 Web Server 上：
cat /etc/ssh/sshd_config | grep PubkeyAuthentication
# 应该是：PubkeyAuthentication yes
```

### 问题 2：端口已被占用

**错误信息：**
```
bind: Address already in use
channel_setup_fwd_listener_tcpip: cannot listen to port: 19000
```

**解决方案：**
```bash
# 在 Web Server 上查找占用端口的进程
netstat -tlnp | grep 19000
lsof -i :19000

# 杀掉占用的进程
kill <PID>

# 或者在 tunnel_config.sh 中修改端口号
REMOTE_MGMT_PORT="19002"  # 使用其他端口
```

### 问题 3：隧道频繁断开

**原因：** 网络不稳定或防火墙超时

**解决方案：**
```bash
# 1. 安装 autossh（自动重连）
apt-get install autossh

# 2. 调整心跳参数（在 tunnel_config.sh 中）
KEEPALIVE_INTERVAL=10  # 减小心跳间隔
KEEPALIVE_TIMEOUT=30   # 减小超时时间

# 3. 使用 systemd 自动重启
sudo systemctl enable ssh-tunnel
```

### 问题 4：无法连接到 GPU Server

**检查步骤：**

1. **在 GPU Server 上：**
```bash
# 检查本地服务是否运行
netstat -tlnp | grep 9000
netstat -tlnp | grep 9001

# 测试本地连接
curl http://localhost:9000/mgmt/health
```

2. **在 Web Server 上：**
```bash
# 检查隧道端口是否监听
netstat -tlnp | grep 19000
netstat -tlnp | grep 19001

# 测试连接
curl http://localhost:19000/mgmt/health
```

3. **检查防火墙：**
```bash
# 在 Web Server 上
# 确保没有防火墙规则阻止本地连接
iptables -L -n | grep 19000
```

---

## 📊 性能对比

### 延迟测试

```bash
# 测试 SSH 隧道延迟
time curl http://localhost:19000/mgmt/health

# 对比之前的 FRP 延迟
# 通常 SSH 隧道的延迟会稍低一些
```

### 带宽测试

```bash
# 使用 iperf3 测试带宽（需要在两端都安装 iperf3）
# 在 Web Server 上：
iperf3 -s -p 19002

# 在 GPU Server 上（通过隧道）：
iperf3 -c localhost -p 19002 -R
```

---

## 🔒 安全建议

1. **使用密钥认证，不要使用密码：**
```bash
# 在 Web Server 的 /etc/ssh/sshd_config 中：
PasswordAuthentication no
PubkeyAuthentication yes
```

2. **限制 SSH 访问 IP：**
```bash
# 在 Web Server 的 /etc/ssh/sshd_config 中：
AllowUsers root@<GPU_SERVER_IP>
```

3. **使用防火墙限制端口访问：**
```bash
# 在 Web Server 上：
# 只允许本地访问隧道端口
iptables -A INPUT -p tcp --dport 19000 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 19000 -j DROP
iptables -A INPUT -p tcp --dport 19001 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 19001 -j DROP
```

4. **定期更新 SSH 密钥：**
```bash
# 每 6 个月更新一次
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa_new -N ""
# 然后更新 authorized_keys
```

---

## 📝 与前端的集成

### Web Server 后端配置

如果你的 Web Server 后端原来配置的是：

```python
# 旧配置（FRP）
GPU_SERVER_API = "http://localhost:19000"
GPU_SERVER_WS = "ws://localhost:19001"
```

**好消息：** 无需修改！SSH 隧道使用相同的端口映射。

### 前端配置

如果前端直接连接 Web Server，也无需修改：

```javascript
// 前端配置保持不变
const API_BASE = '/api/gpu';  // 通过 Web Server 代理
const WS_URL = 'ws://your-domain.com/ws/gpu';
```

---

## 📚 参考文档

- [SSH Port Forwarding](https://www.ssh.com/academy/ssh/tunneling/example)
- [AutoSSH Documentation](https://www.harding.motd.ca/autossh/)
- [Systemd Service Management](https://www.freedesktop.org/software/systemd/man/systemd.service.html)

---

## ✅ 迁移检查清单

- [ ] 在 GPU Server 上安装 SSH 客户端和 autossh
- [ ] 生成 SSH 密钥并添加到 Web Server
- [ ] 测试 SSH 连接
- [ ] 配置 tunnel_config.sh
- [ ] 给脚本添加执行权限
- [ ] 启动 SSH 隧道
- [ ] 验证端口映射
- [ ] 测试 API 和 WebSocket 连接
- [ ] 停止旧的 FRP 服务
- [ ] （可选）配置开机自动启动
- [ ] 更新文档和监控配置

---

## 🆘 获取帮助

如果遇到问题：

1. 查看日志：`tail -f /workspace/gpuserver/logs/ssh_tunnel.log`
2. 检查状态：`./status_tunnel.sh`
3. 测试 SSH 连接：`ssh -v root@51.161.130.234`
4. 查看进程：`ps aux | grep ssh`
5. 查看网络连接：`netstat -an | grep 19000`

---

## 📈 下一步

迁移完成后，建议：

1. 监控隧道稳定性（7 天）
2. 测试在网络中断后的自动恢复
3. 配置告警（隧道断开时发送通知）
4. 文档化你的具体配置
5. 删除 FRP 相关文件和配置

祝迁移顺利！🎉
