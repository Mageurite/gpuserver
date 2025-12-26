#!/bin/bash
#
# GPU Server 一键停止脚本
# 停止 GPU Server 和 FRP
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
echo "=========================================="
echo "  GPU Server - 停止所有服务"
echo "=========================================="
echo ""

# 1. 停止 GPU Server
echo "正在停止 GPU Server..."

# 停止所有 unified_server.py 进程
if pgrep -f "python.*unified_server.py" > /dev/null; then
    pkill -f "python.*unified_server.py"
    echo -e "${GREEN}✓ GPU Server 已停止${NC}"
else
    echo -e "${YELLOW}GPU Server 未运行${NC}"
fi

# 清理 PID 文件
if [ -f "logs/server.pid" ]; then
    rm -f logs/server.pid
fi

# 2. 停止 FRP
echo ""
echo "正在停止 FRP..."

if pgrep -f "frpc" > /dev/null; then
    if [ -f "stop_frpc.sh" ]; then
        bash stop_frpc.sh
    elif [ -f "temp/scripts/stop_frpc.sh" ]; then
        bash temp/scripts/stop_frpc.sh
    else
        pkill -9 -f "frpc"
    fi
    echo -e "${GREEN}✓ FRP 已停止${NC}"
else
    echo -e "${YELLOW}FRP 未运行${NC}"
fi

# 3. 检查端口
echo ""
echo "检查端口占用..."

MANAGEMENT_API_PORT=${MANAGEMENT_API_PORT:-9000}

if lsof -i :${MANAGEMENT_API_PORT} > /dev/null 2>&1; then
    echo -e "${YELLOW}! 端口 ${MANAGEMENT_API_PORT} 仍被占用${NC}"
    echo "  请手动检查: lsof -i :${MANAGEMENT_API_PORT}"
else
    echo -e "${GREEN}✓ 端口 ${MANAGEMENT_API_PORT} 已释放${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}  所有服务已停止${NC}"
echo "=========================================="
echo ""
