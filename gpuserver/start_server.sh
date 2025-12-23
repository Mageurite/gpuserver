#!/bin/bash
#
# GPU Server - 启动脚本（宿主机版本，不使用 Docker）
# 用途：在宿主机上启动 GPU Server 和 frpc
#

set -e

echo "========================================="
echo "  Virtual Tutor GPU Server 启动"
echo "  (宿主机版本 + frp 反向隧道)"
echo "========================================="
echo ""

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误：未找到 Python3"
    echo "请先安装 Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✅ Python 版本: $PYTHON_VERSION"
echo ""

# 检查虚拟环境
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    echo "⚠️  未检测到虚拟环境"
    read -p "是否创建虚拟环境？(y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "📦 创建虚拟环境..."
        python3 -m venv venv
        echo "✅ 虚拟环境创建完成"
    fi
fi

# 激活虚拟环境
if [ -f "venv/bin/activate" ]; then
    echo "🔧 激活虚拟环境..."
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    echo "🔧 激活虚拟环境..."
    source .venv/bin/activate
fi

# 检查依赖
if [ -f "requirements.txt" ]; then
    echo "📦 检查 Python 依赖..."
    pip install -q -r requirements.txt
    echo "✅ 依赖检查完成"
    echo ""
fi

# 检查配置文件
if [ ! -f ".env" ]; then
    echo "⚠️  未找到 .env 配置文件"
    if [ -f ".env.frp" ]; then
        echo "📝 使用 .env.frp 作为模板..."
        cp .env.frp .env
        echo "✅ 已创建 .env 文件"
        echo "   请编辑 .env，修改 WEBSOCKET_URL"
    else
        echo "❌ 错误：未找到配置文件"
        exit 1
    fi
fi

# 检查是否已启动
if pgrep -f "python.*server.py" > /dev/null; then
    echo "⚠️  检测到 GPU Server 已在运行"
    read -p "是否停止并重启？(y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🛑 停止旧的进程..."
        pkill -f "python.*server.py" || true
        sleep 2
    else
        echo "已取消启动"
        exit 0
    fi
fi

# 询问是否启动 frpc
echo ""
echo "📡 frpc 配置："
read -p "是否同时启动 frpc？(y/n): " -n 1 -r
echo ""
START_FRPC=$REPLY

if [[ $START_FRPC =~ ^[Yy]$ ]]; then
    # 启动 frpc
    if [ -f "./start_frpc.sh" ]; then
        echo "🚀 启动 frpc..."
        ./start_frpc.sh
        echo ""
    else
        echo "⚠️  未找到 start_frpc.sh"
        echo "   请手动启动 frpc"
        echo ""
    fi
fi

# 创建日志目录
mkdir -p logs

# 启动 GPU Server
echo ""
echo "🚀 启动 GPU Server..."
echo ""
echo "请选择启动方式："
echo "  1) 前台运行（可以看到实时日志，Ctrl+C 停止）"
echo "  2) 后台运行（推荐，持久运行）"
echo ""
read -p "请选择 (1/2): " -n 1 -r
echo ""
echo ""

if [[ $REPLY == "1" ]]; then
    # 前台运行
    echo "🚀 前台启动 GPU Server..."
    echo "   按 Ctrl+C 停止"
    echo ""
    exec python3 -u server.py
else
    # 后台运行
    LOG_FILE="logs/gpu_server.log"

    echo "🚀 后台启动 GPU Server..."
    nohup python3 -u server.py > $LOG_FILE 2>&1 &
    SERVER_PID=$!

    # 等待启动
    sleep 3

    # 检查是否启动成功
    if ps -p $SERVER_PID > /dev/null; then
        echo "✅ GPU Server 启动成功！"
        echo ""
        echo "📊 服务信息："
        echo "   - PID: $SERVER_PID"
        echo "   - 日志文件: $LOG_FILE"
        echo "   - Management API: http://localhost:9000"
        echo "   - WebSocket: ws://localhost:9001"
        echo ""
        if [[ $START_FRPC =~ ^[Yy]$ ]]; then
            echo "📡 通过 frp 访问（从外部）："
            echo "   - Management API: http://WEB_SERVER_IP:9000"
            echo "   - WebSocket: ws://WEB_SERVER_IP:9001"
            echo ""
        fi
        echo "🔍 查看日志："
        echo "   tail -f $LOG_FILE"
        echo ""
        echo "🛑 停止服务："
        echo "   kill $SERVER_PID"
        echo "   或: pkill -f 'python.*server.py'"
        echo ""
        echo "📝 最近日志："
        tail -20 $LOG_FILE
    else
        echo "❌ GPU Server 启动失败"
        echo "查看日志: cat $LOG_FILE"
        exit 1
    fi
fi

echo ""
echo "========================================="
echo "  GPU Server 启动完成！"
echo "========================================="
