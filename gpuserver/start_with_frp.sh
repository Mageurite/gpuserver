#!/bin/bash
#
# GPU Server - 快速启动脚本（带 frpc）
# 用途：在 GPU Server 上快速启动服务，自动配置和启动 frpc
#

set -e

echo "========================================="
echo "  Virtual Tutor GPU Server 启动"
echo "  (with frp reverse tunnel)"
echo "========================================="
echo ""

# 检查是否在正确的目录
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ 错误：请在 gpuserver 目录下运行此脚本"
    exit 1
fi

# 检查 frpc 配置
FRPC_CONFIG="../frp_config/frpc.ini"
if [ ! -f "$FRPC_CONFIG" ]; then
    echo "❌ 错误：找不到 frpc.ini 配置文件"
    echo "   预期位置: $FRPC_CONFIG"
    echo "   请先配置 frpc.ini"
    exit 1
fi

# 检查配置是否已修改
SERVER_ADDR=$(grep "server_addr" $FRPC_CONFIG | awk '{print $3}')
if [ "$SERVER_ADDR" = "YOUR_WEB_SERVER_IP" ]; then
    echo "⚠️  警告：frpc.ini 中的 server_addr 尚未配置"
    echo "   当前值: $SERVER_ADDR"
    echo ""
    read -p "请输入 Web Server 的 IP 地址: " WEB_SERVER_IP

    if [ -z "$WEB_SERVER_IP" ]; then
        echo "❌ 错误：IP 地址不能为空"
        exit 1
    fi

    # 替换配置文件
    sed -i "s/YOUR_WEB_SERVER_IP/$WEB_SERVER_IP/g" $FRPC_CONFIG
    echo "✅ 已更新 server_addr 为: $WEB_SERVER_IP"
    echo ""
fi

# 复制 frpc 配置到容器挂载目录
echo "📁 准备 frpc 配置..."
mkdir -p ./frp_config
cp $FRPC_CONFIG ./frp_config/

# 停止旧容器
echo "🛑 停止旧容器（如果存在）..."
docker-compose down 2>/dev/null || true

# 启动服务
echo "🚀 启动 GPU Server..."
docker-compose up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查服务状态
echo "🔍 检查服务状态..."
if docker ps | grep -q gpu-server; then
    echo "✅ GPU Server 启动成功！"
    echo ""

    # 在容器内安装和启动 frpc
    echo "🔧 安装和启动 frpc..."
    docker exec gpu-server /app/install_and_start_frpc.sh &

    echo ""
    echo "📊 服务信息："
    echo "   - 容器名称: gpu-server"
    echo "   - Management API: localhost:9000 (容器内)"
    echo "   - WebSocket: localhost:9001 (容器内)"
    echo "   - frp 连接到: $SERVER_ADDR:7000"
    echo ""
    echo "📝 通过 frp 访问："
    echo "   - Management API: http://${SERVER_ADDR}:9000"
    echo "   - WebSocket: ws://${SERVER_ADDR}:9001"
    echo ""
    echo "🔍 查看日志："
    echo "   docker logs -f gpu-server"
    echo ""
    echo "🛑 停止服务："
    echo "   docker-compose down"
    echo ""
else
    echo "❌ GPU Server 启动失败"
    echo "查看日志: docker logs gpu-server"
    exit 1
fi

echo "========================================="
echo "  GPU Server 启动完成！"
echo "========================================="
