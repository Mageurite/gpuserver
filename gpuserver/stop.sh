#!/bin/bash
# GPU Server 停止脚本
# 停止所有 GPU Server 相关进程

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=========================================="
echo "  GPU Server - 停止服务"
echo "=========================================="
echo ""

# 停止统一服务器
echo "正在停止 GPU Server..."

# 方法 1: 通过 PID 文件停止
if [ -f "logs/server.pid" ]; then
    PID=$(cat logs/server.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "停止进程 (PID: $PID)..."
        kill $PID 2>/dev/null || true

        # 等待进程结束
        for i in {1..10}; do
            if ! ps -p $PID > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done

        # 如果还没结束，强制杀死
        if ps -p $PID > /dev/null 2>&1; then
            echo "强制停止进程..."
            kill -9 $PID 2>/dev/null || true
        fi
    fi
    rm -f logs/server.pid
fi

# 方法 2: 通过进程名停止（确保清理所有残留进程）
if pgrep -f "python.*unified_server.py" > /dev/null; then
    echo "停止所有 unified_server.py 进程..."
    pkill -f "python.*unified_server.py" || true
    sleep 2

    # 强制杀死残留进程
    if pgrep -f "python.*unified_server.py" > /dev/null; then
        echo "强制停止残留进程..."
        pkill -9 -f "python.*unified_server.py" || true
    fi
fi

# 停止旧的分离模式进程（如果有）
if pgrep -f "python.*management_api.py" > /dev/null; then
    echo "停止 management_api.py 进程..."
    pkill -f "python.*management_api.py" || true
fi

if pgrep -f "python.*websocket_server.py" > /dev/null; then
    echo "停止 websocket_server.py 进程..."
    pkill -f "python.*websocket_server.py" || true
fi

# 等待所有进程完全退出
sleep 1

# 检查是否还有残留进程
if pgrep -f "python.*(unified_server|management_api|websocket_server).py" > /dev/null; then
    echo -e "${YELLOW}警告: 仍有残留进程在运行${NC}"
    echo "残留进程列表:"
    pgrep -af "python.*(unified_server|management_api|websocket_server).py" || true
    echo ""
    echo "可以手动强制停止: pkill -9 -f 'python.*unified_server.py'"
else
    echo -e "${GREEN}✓ GPU Server 已完全停止${NC}"
fi

# 检查端口占用
PORT=${MANAGEMENT_API_PORT:-9000}
if lsof -i :$PORT > /dev/null 2>&1; then
    echo -e "${YELLOW}警告: 端口 $PORT 仍被占用${NC}"
    echo "占用端口的进程:"
    lsof -i :$PORT || true
else
    echo -e "${GREEN}✓ 端口 $PORT 已释放${NC}"
fi

echo ""
echo "=========================================="

# 停止 FRP（如果在运行）
if pgrep -f "frpc" > /dev/null; then
    echo ""
    echo "检测到 FRP 正在运行"
    read -p "是否同时停止 FRP？(Y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        echo "正在停止 FRP..."
        if [ -f "stop_frpc.sh" ]; then
            bash stop_frpc.sh
        else
            pkill -9 -f "frpc" || true
            echo -e "${GREEN}✓ FRP 已停止${NC}"
        fi
    fi
fi

echo ""
echo "=========================================="
