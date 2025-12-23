#!/bin/bash
#
# 在运行中的容器内安装并启动 frpc
# 用途：临时方案，容器重启后会丢失
# 使用：在容器内直接运行此脚本
#

set -e

echo "========================================="
echo "  在容器内安装 frp Client (临时方案)"
echo "========================================="
echo ""

# 检查是否在容器内
if [ -f /.dockerenv ]; then
    echo "✅ 检测到 Docker 容器环境"
else
    echo "⚠️  警告：未检测到容器环境"
fi
echo ""

FRP_VERSION="0.56.0"
FRP_DIR="/opt/frp"
FRPC_BIN="/usr/local/bin/frpc"

# ============================================
# 1. 安装 frpc
# ============================================
echo "📥 下载 frp ${FRP_VERSION}..."

cd /tmp
wget -q https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_amd64.tar.gz

echo "📦 解压..."
tar -xzf frp_${FRP_VERSION}_linux_amd64.tar.gz
cd frp_${FRP_VERSION}_linux_amd64

echo "📋 安装 frpc..."
cp frpc $FRPC_BIN
chmod +x $FRPC_BIN

# 验证安装
$FRPC_BIN --version
echo ""

# ============================================
# 2. 创建配置文件
# ============================================
echo "⚙️  创建配置文件..."
mkdir -p $FRP_DIR

# 检查是否已有配置文件
if [ -f "/workspace/gpuserver/frpc.ini" ]; then
    echo "✅ 发现已有配置文件，直接使用"
    cp /workspace/gpuserver/frpc.ini ${FRP_DIR}/frpc.ini

    SERVER_ADDR=$(grep "server_addr" ${FRP_DIR}/frpc.ini | awk '{print $3}')
    TOKEN=$(grep "^token" ${FRP_DIR}/frpc.ini | awk '{print $3}')

    echo ""
    echo "📋 配置信息："
    echo "   Web Server: ${SERVER_ADDR}"
    echo "   Token: ${TOKEN}"
    echo ""
else
    echo ""
    echo "请输入配置信息："
    read -p "Web Server IP 地址: " SERVER_ADDR

    if [ -z "$SERVER_ADDR" ]; then
        echo "❌ 错误：IP 地址不能为空"
        exit 1
    fi

    read -p "frp Server Port (默认 7000): " SERVER_PORT
    SERVER_PORT=${SERVER_PORT:-7000}

    read -p "Token: " TOKEN

    # 创建配置文件
    cat > ${FRP_DIR}/frpc.ini << EOF
[common]
server_addr = ${SERVER_ADDR}
server_port = ${SERVER_PORT}
token = ${TOKEN}

log_file = /app/logs/frpc.log
log_level = info
log_max_days = 7

heartbeat_interval = 30
heartbeat_timeout = 90

tcp_mux = true
login_fail_exit = false

[gpu_management_api]
type = tcp
local_ip = 127.0.0.1
local_port = 9000
remote_port = 9000

[gpu_websocket]
type = tcp
local_ip = 127.0.0.1
local_port = 9001
remote_port = 9001
EOF

    echo "✅ 配置文件已创建: ${FRP_DIR}/frpc.ini"
    echo ""
fi

# ============================================
# 3. 启动 frpc
# ============================================
echo "🚀 启动 frpc..."
echo ""
echo "请选择启动方式："
echo "  1) 前台运行（测试用，Ctrl+C 停止）"
echo "  2) 后台运行（推荐）"
echo ""
read -p "请选择 (1/2): " -n 1 -r
echo ""
echo ""

# 创建日志目录
mkdir -p /app/logs

if [[ $REPLY == "1" ]]; then
    # 前台运行
    echo "🚀 前台启动 frpc（按 Ctrl+C 停止）..."
    echo ""
    exec frpc -c ${FRP_DIR}/frpc.ini
else
    # 后台运行
    echo "🚀 后台启动 frpc..."
    nohup frpc -c ${FRP_DIR}/frpc.ini > /app/logs/frpc.log 2>&1 &
    FRPC_PID=$!

    # 等待启动
    sleep 3

    # 检查是否启动成功
    if ps -p $FRPC_PID > /dev/null 2>&1; then
        echo "✅ frpc 启动成功！"
        echo ""
        echo "📊 进程信息："
        echo "   - PID: $FRPC_PID"
        echo "   - 配置文件: ${FRP_DIR}/frpc.ini"
        echo "   - 日志文件: /app/logs/frpc.log"
        echo ""
        echo "🔍 查看日志："
        echo "   tail -f /app/logs/frpc.log"
        echo ""
        echo "🛑 停止 frpc："
        echo "   kill $FRPC_PID"
        echo "   或: pkill -f frpc"
        echo ""
        echo "📝 连接状态："
        sleep 2
        tail -20 /app/logs/frpc.log 2>/dev/null || echo "日志生成中..."
    else
        echo "❌ frpc 启动失败"
        echo "查看日志: cat /app/logs/frpc.log"
        exit 1
    fi
fi

# 清理
cd /
rm -rf /tmp/frp_${FRP_VERSION}_linux_amd64*

echo ""
echo "========================================="
echo "  安装完成！"
echo "========================================="
echo ""
echo "⚠️  重要提示："
echo "   这是临时安装，容器重启后会丢失"
echo "   建议联系管理员使用 Dockerfile 方案"
echo ""
