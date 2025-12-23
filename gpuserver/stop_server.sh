#!/bin/bash
#
# GPU Server - 停止脚本（宿主机版本）
# 用途：停止 GPU Server 和 frpc
#

set -e

echo "========================================="
echo "  Virtual Tutor GPU Server 停止"
echo "========================================="
echo ""

STOPPED_ANY=0

# 停止 GPU Server
if pgrep -f "python.*server.py" > /dev/null; then
    echo "🔍 检测到 GPU Server 进程："
    ps aux | grep "python.*server.py" | grep -v grep
    echo ""
    read -p "是否停止 GPU Server？(y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🛑 停止 GPU Server..."
        pkill -f "python.*server.py" || true
        sleep 1
        if pgrep -f "python.*server.py" > /dev/null; then
            echo "⚠️  进程未完全停止，使用强制停止..."
            pkill -9 -f "python.*server.py" || true
        fi
        echo "✅ GPU Server 已停止"
        STOPPED_ANY=1
    fi
    echo ""
fi

# 停止 frpc
if pgrep -f "frpc.*frpc.ini" > /dev/null; then
    echo "🔍 检测到 frpc 进程："
    ps aux | grep "frpc.*frpc.ini" | grep -v grep
    echo ""
    read -p "是否停止 frpc？(y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🛑 停止 frpc..."
        pkill -f "frpc.*frpc.ini" || true
        sleep 1
        if pgrep -f "frpc.*frpc.ini" > /dev/null; then
            echo "⚠️  进程未完全停止，使用强制停止..."
            pkill -9 -f "frpc.*frpc.ini" || true
        fi
        echo "✅ frpc 已停止"
        STOPPED_ANY=1
    fi
    echo ""
fi

if [ $STOPPED_ANY -eq 0 ]; then
    echo "❌ 未检测到运行中的进程"
fi

echo "========================================="
echo "  完成！"
echo "========================================="
