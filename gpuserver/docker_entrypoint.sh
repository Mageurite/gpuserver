#!/bin/bash
#
# Docker 容器统一启动脚本
# 功能：先启动 frpc，再启动 GPU Server 应用
#

set -e

echo "========================================="
echo "  Virtual Tutor GPU Server"
echo "  (Container with frp reverse tunnel)"
echo "========================================="
echo ""

# ============================================
# 1. 启动 frp client
# ============================================
if [ -f "/opt/frp/frpc.ini" ]; then
    echo "🚀 启动 frp client..."

    # 检查配置
    SERVER_ADDR=$(grep "server_addr" /opt/frp/frpc.ini | awk '{print $3}')

    if [ "$SERVER_ADDR" = "YOUR_WEB_SERVER_IP" ]; then
        echo "⚠️  警告: frpc.ini 中的 server_addr 未配置"
        echo "   请修改 frpc.ini 或使用环境变量 FRP_SERVER_ADDR"

        # 尝试使用环境变量
        if [ -n "$FRP_SERVER_ADDR" ]; then
            echo "   使用环境变量: FRP_SERVER_ADDR=$FRP_SERVER_ADDR"
            sed -i "s/YOUR_WEB_SERVER_IP/$FRP_SERVER_ADDR/g" /opt/frp/frpc.ini
        fi
    fi

    # 后台启动 frpc
    nohup frpc -c /opt/frp/frpc.ini > /app/logs/frpc.log 2>&1 &
    FRPC_PID=$!

    echo "   frpc PID: $FRPC_PID"
    echo "   frpc 日志: /app/logs/frpc.log"

    # 等待 frpc 连接建立
    echo "   等待 frpc 连接..."
    sleep 3

    # 检查 frpc 是否运行
    if ps -p $FRPC_PID > /dev/null; then
        echo "✅ frpc 启动成功！"
    else
        echo "⚠️  frpc 启动异常，查看日志: tail -f /app/logs/frpc.log"
    fi
    echo ""
else
    echo "⚠️  未找到 frpc.ini，跳过 frp client 启动"
    echo "   如需使用 frp，请确保 /opt/frp/frpc.ini 存在"
    echo ""
fi

# ============================================
# 2. 启动 GPU Server 应用
# ============================================
echo "🚀 启动 GPU Server..."
echo "   命令: $@"
echo ""

# 使用 exec 替换当前进程，确保信号正确传递
exec "$@"
