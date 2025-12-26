#!/bin/bash
#
# GPU Server - frpc 停止脚本
#

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "========================================="
echo "  停止 frpc"
echo "========================================="
echo ""

# 检查 PID 文件
if [ -f "logs/frpc.pid" ]; then
    PID=$(cat logs/frpc.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "停止 frpc 进程 (PID: $PID)..."
        kill -15 $PID
        sleep 2

        # 如果还在运行，强制停止
        if ps -p $PID > /dev/null 2>&1; then
            echo "强制停止..."
            kill -9 $PID
        fi

        echo -e "${GREEN}✅ frpc 已停止${NC}"
        rm -f logs/frpc.pid
    else
        echo -e "${YELLOW}进程不存在 (PID: $PID)${NC}"
        rm -f logs/frpc.pid
    fi
fi

# 清理所有 frpc 进程
if pgrep -f "frpc.*\.ini" > /dev/null; then
    echo "清理残留的 frpc 进程..."
    pkill -9 -f "frpc.*\.ini"
    echo -e "${GREEN}✅ 已清理所有 frpc 进程${NC}"
else
    echo -e "${GREEN}✅ 无运行中的 frpc 进程${NC}"
fi

echo ""
echo "========================================="
echo "  frpc 已停止"
echo "========================================="
echo ""
