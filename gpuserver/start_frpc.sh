#!/bin/bash
#
# GPU Server - frpc 启动脚本（宿主机版本）
# 用途：在宿主机上启动 frpc，连接到 Web Server
#

set -e

echo "========================================="
echo "  frpc 启动脚本"
echo "========================================="
echo ""

# 检测 frpc 路径
if command -v frpc &> /dev/null; then
    FRPC_BIN=$(which frpc)
elif [ -f "/usr/local/frp/frpc" ]; then
    FRPC_BIN="/usr/local/frp/frpc"
elif [ -f "$HOME/frp/frpc" ]; then
    FRPC_BIN="$HOME/frp/frpc"
else
    echo "❌ 错误：未找到 frpc"
    echo "   请先运行: ./install_frpc_host.sh"
    exit 1
fi

echo "✅ 找到 frpc: $FRPC_BIN"
$FRPC_BIN --version
echo ""

# 检测配置文件
CONFIG_FILE=""
if [ -f "$HOME/.frp/frpc.ini" ]; then
    CONFIG_FILE="$HOME/.frp/frpc.ini"
elif [ -f "../frp_config/frpc.ini" ]; then
    CONFIG_FILE="../frp_config/frpc.ini"
elif [ -f "./frpc.ini" ]; then
    CONFIG_FILE="./frpc.ini"
else
    echo "❌ 错误：未找到配置文件 frpc.ini"
    echo "   请将 frpc.ini 放置在以下位置之一："
    echo "   - $HOME/.frp/frpc.ini"
    echo "   - ../frp_config/frpc.ini"
    echo "   - ./frpc.ini"
    exit 1
fi

echo "📁 使用配置文件: $CONFIG_FILE"
echo ""

# 检查配置是否已修改
SERVER_ADDR=$(grep "server_addr" $CONFIG_FILE | awk '{print $3}')
if [ "$SERVER_ADDR" = "YOUR_WEB_SERVER_IP" ]; then
    echo "⚠️  警告：配置文件中的 server_addr 尚未配置"
    echo "   当前值: $SERVER_ADDR"
    echo ""
    read -p "请输入 Web Server 的 IP 地址: " WEB_SERVER_IP

    if [ -z "$WEB_SERVER_IP" ]; then
        echo "❌ 错误：IP 地址不能为空"
        exit 1
    fi

    # 替换配置文件
    sed -i.bak "s/YOUR_WEB_SERVER_IP/$WEB_SERVER_IP/g" $CONFIG_FILE
    echo "✅ 已更新 server_addr 为: $WEB_SERVER_IP"
    echo "   备份文件: ${CONFIG_FILE}.bak"
    echo ""
fi

# 检查是否已经运行
if pgrep -f "frpc.*frpc.ini" > /dev/null; then
    echo "⚠️  检测到 frpc 已在运行"
    echo ""
    read -p "是否停止并重启？(y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🛑 停止旧的 frpc 进程..."
        pkill -f "frpc.*frpc.ini" || true
        sleep 2
    else
        echo "已取消启动"
        exit 0
    fi
fi

# 询问启动方式
echo "请选择启动方式："
echo "  1) 前台运行（可以看到实时日志，Ctrl+C 停止）"
echo "  2) 后台运行（推荐，持久运行）"
echo ""
read -p "请选择 (1/2): " -n 1 -r
echo ""
echo ""

if [[ $REPLY == "1" ]]; then
    # 前台运行
    echo "🚀 前台启动 frpc..."
    echo "   按 Ctrl+C 停止"
    echo ""
    exec $FRPC_BIN -c $CONFIG_FILE
else
    # 后台运行
    LOG_DIR="$HOME/.frp"
    mkdir -p $LOG_DIR
    LOG_FILE="$LOG_DIR/frpc.log"

    echo "🚀 后台启动 frpc..."
    nohup $FRPC_BIN -c $CONFIG_FILE > $LOG_FILE 2>&1 &
    FRPC_PID=$!

    # 等待启动
    sleep 2

    # 检查是否启动成功
    if ps -p $FRPC_PID > /dev/null; then
        echo "✅ frpc 启动成功！"
        echo ""
        echo "📊 进程信息："
        echo "   - PID: $FRPC_PID"
        echo "   - 日志文件: $LOG_FILE"
        echo "   - 配置文件: $CONFIG_FILE"
        echo ""
        echo "🔍 查看日志："
        echo "   tail -f $LOG_FILE"
        echo ""
        echo "🛑 停止 frpc："
        echo "   kill $FRPC_PID"
        echo "   或: pkill -f 'frpc.*frpc.ini'"
        echo ""
        echo "📝 查看连接状态："
        tail -20 $LOG_FILE
    else
        echo "❌ frpc 启动失败"
        echo "查看日志: cat $LOG_FILE"
        exit 1
    fi
fi

echo ""
echo "========================================="
echo "  frpc 启动完成！"
echo "========================================="
