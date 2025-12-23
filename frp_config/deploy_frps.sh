#!/bin/bash
#
# Web Server - frp Server 部署脚本
# 用途：在 Web Server 上部署 frps，接收 GPU Server 的反向隧道
#

set -e

echo "========================================="
echo "  Virtual Tutor - frps 部署脚本"
echo "  用途：在 Web Server 上部署 frp Server"
echo "========================================="
echo ""

# 检查 Docker 和 Docker Compose
if ! command -v docker &> /dev/null; then
    echo "❌ 错误：未安装 Docker"
    echo "请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ 错误：未安装 Docker Compose"
    echo "请先安装 Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# 检查配置文件
if [ ! -f "frps.ini" ]; then
    echo "❌ 错误：找不到 frps.ini 配置文件"
    echo "请确保在 frp_config 目录下运行此脚本"
    exit 1
fi

# 读取当前 IP
echo "🔍 检测当前服务器 IP..."
CURRENT_IP=$(hostname -I | awk '{print $1}')
echo "   当前内网 IP: $CURRENT_IP"

# 获取公网 IP（如果有）
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "未检测到")
if [ "$PUBLIC_IP" != "未检测到" ]; then
    echo "   公网 IP: $PUBLIC_IP"
fi

echo ""
echo "⚠️  重要提示："
echo "   GPU Server 需要使用此 IP 地址连接"
echo "   请将 frpc.ini 中的 server_addr 修改为上述 IP"
echo ""

# 询问是否继续
read -p "是否继续部署 frps？(y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消部署"
    exit 0
fi

# 创建日志目录
echo "📁 创建日志目录..."
mkdir -p frps_logs

# 停止旧容器（如果存在）
echo "🛑 停止旧的 frps 容器（如果存在）..."
docker stop frps 2>/dev/null || true
docker rm frps 2>/dev/null || true

# 启动 frps
echo "🚀 启动 frps..."
if command -v docker-compose &> /dev/null; then
    docker-compose -f docker-compose.frps.yml up -d
else
    docker compose -f docker-compose.frps.yml up -d
fi

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查服务状态
echo "🔍 检查服务状态..."
if docker ps | grep -q frps; then
    echo "✅ frps 启动成功！"
    echo ""
    echo "📊 服务信息："
    echo "   - frp 服务端口: 7000"
    echo "   - Dashboard: http://${CURRENT_IP}:7500"
    echo "   - Dashboard 用户名: admin"
    echo "   - Dashboard 密码: VirtualTutor2024!"
    echo ""
    echo "🔌 转发端口："
    echo "   - GPU Management API: ${CURRENT_IP}:9000"
    echo "   - GPU WebSocket: ${CURRENT_IP}:9001"
    echo ""
    echo "📝 下一步："
    echo "   1. 在 GPU Server 上配置 frpc.ini，将 server_addr 设置为: $CURRENT_IP"
    echo "   2. 在 GPU Server 上运行 frpc"
    echo "   3. 在 Web Server 后端配置 ENGINE_URL=http://${CURRENT_IP}:9000"
    echo ""
    echo "🔍 查看日志："
    echo "   docker logs -f frps"
    echo ""
else
    echo "❌ frps 启动失败"
    echo "查看日志: docker logs frps"
    exit 1
fi

# 防火墙提示
echo "⚠️  防火墙配置提示："
echo "   如果连接失败，请确保防火墙已开放以下端口："
echo "   - 7000 (frp 服务，必须开放)"
echo "   - 9000 (GPU API，必须开放)"
echo "   - 9001 (GPU WebSocket，必须开放)"
echo "   - 7500 (Dashboard，可选)"
echo ""
echo "   Ubuntu/Debian 示例："
echo "   sudo ufw allow 7000/tcp"
echo "   sudo ufw allow 9000/tcp"
echo "   sudo ufw allow 9001/tcp"
echo ""
echo "========================================="
echo "  frps 部署完成！"
echo "========================================="
