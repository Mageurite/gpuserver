# frp 反向隧道快速开始指南

## 🚀 5 分钟快速部署

### 前置条件

- Web Server 有公网 IP 或可访问的域名
- 两台服务器都安装了 Docker 和 Docker Compose
- GPU Server 可以访问外网（至少能连接到 Web Server）

---

## 步骤 1：部署 Web Server 端 (2 分钟)

```bash
# 在 Web Server 上执行

# 1. 进入 frp_config 目录
cd /workspace/frp_config

# 2. （可选）修改 token
# vim frps.ini  # 修改 token 为更强的密码

# 3. 运行部署脚本
./deploy_frps.sh

# 4. 记录显示的 IP 地址（下一步需要）
# 示例输出：当前内网 IP: 192.168.1.100
```

**预期结果**：
```
✅ frps 启动成功！
📊 服务信息：
   - frp 服务端口: 7000
   - Dashboard: http://192.168.1.100:7500
```

---

## 步骤 2：部署 GPU Server 端 (3 分钟)

```bash
# 在 GPU Server 上执行

# 1. 进入 gpuserver 目录
cd /workspace/gpuserver

# 2. 运行快速启动脚本
./start_with_frp.sh

# 脚本会提示输入 Web Server IP，输入步骤 1 记录的 IP
# 例如：192.168.1.100
```

**预期结果**：
```
✅ GPU Server 启动成功！
📊 服务信息：
   - 通过 frp 访问：
   - Management API: http://192.168.1.100:9000
   - WebSocket: ws://192.168.1.100:9001
```

---

## 步骤 3：验证连接 (1 分钟)

```bash
# 在 Web Server 上执行

# 测试 GPU Server API
curl http://localhost:9000/health

# 预期响应
{
  "status": "healthy",
  ...
}
```

---

## ✅ 完成！

现在你可以：

1. **配置 Web Server 后端**：
   ```bash
   cd /path/to/virtual_tutor/app_backend
   vim .env
   # 设置：ENGINE_URL=http://localhost:9000
   ```

2. **启动 Web Server**：
   ```bash
   # 启动前端和后端
   ./start.sh
   ```

3. **测试端到端**：
   - 访问 `http://WEB_SERVER_IP:3000`
   - 创建 Tutor，添加 Student
   - 测试实时对话功能

---

## 🔍 监控和日志

```bash
# 查看 frps 状态（Web Server）
docker logs -f frps

# 查看 GPU Server 状态
docker logs -f gpu-server

# 访问 frps Dashboard
# http://WEB_SERVER_IP:7500
# 用户名: admin, 密码: VirtualTutor2024!
```

---

## 📋 端口清单

| 服务 | 端口 | 说明 |
|------|------|------|
| frps 服务 | 7000 | GPU Server 连接端口（必须开放） |
| GPU Management API | 9000 | 转发到 GPU Server（必须开放） |
| GPU WebSocket | 9001 | 转发到 GPU Server（必须开放） |
| frps Dashboard | 7500 | 监控界面（可选） |

---

## ⚠️ 常见问题

**Q1: 连接失败怎么办？**

检查防火墙：
```bash
# Ubuntu/Debian
sudo ufw status
sudo ufw allow 7000/tcp
sudo ufw allow 9000/tcp
sudo ufw allow 9001/tcp
```

**Q2: 如何重启服务？**

```bash
# 重启 Web Server frps
docker-compose -f docker-compose.frps.yml restart

# 重启 GPU Server
docker-compose restart
docker exec gpu-server /app/install_and_start_frpc.sh &
```

**Q3: 如何查看详细日志？**

```bash
# frps 日志
docker logs -f frps

# frpc 日志（在 GPU Server 容器内）
docker exec gpu-server cat /app/frp/frpc.log
```

---

详细文档请参考：[FRP_DEPLOYMENT_GUIDE.md](FRP_DEPLOYMENT_GUIDE.md)
