#!/bin/bash
#
# GPU Server - frpc 停止脚本
# 用途：停止运行中的 frpc 进程
#

set -e

echo "========================================="
echo "  frpc 停止脚本"
echo "========================================="
echo ""

# 检查是否有 frpc 进程
if ! pgrep -f "frpc.*frpc.ini" > /dev/null; then
    echo "❌ 未检测到运行中的 frpc 进程"
    exit 0
fi

# 显示运行中的进程
echo "🔍 检测到以下 frpc 进程："
ps aux | grep "frpc.*frpc.ini" | grep -v grep
echo ""

read -p "是否停止这些进程？(y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🛑 停止 frpc..."
    pkill -f "frpc.*frpc.ini" || true
    sleep 1

    # 检查是否停止成功
    if pgrep -f "frpc.*frpc.ini" > /dev/null; then
        echo "⚠️  进程未完全停止，使用强制停止..."
        pkill -9 -f "frpc.*frpc.ini" || true
    fi

    echo "✅ frpc 已停止"
else
    echo "已取消"
fi

echo ""
echo "========================================="
