#!/bin/bash
# GPU Server 停止脚本

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

print_info "GPU Server 停止脚本"
echo "================================"

# 检查 PID 文件
PID_FILE="$SCRIPT_DIR/websocket_server.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    print_info "从 PID 文件读取: $PID"

    # 检查进程是否存在
    if ps -p $PID > /dev/null 2>&1; then
        print_info "停止进程 $PID..."
        kill $PID

        # 等待进程结束
        for i in {1..10}; do
            if ! ps -p $PID > /dev/null 2>&1; then
                print_success "进程已停止"
                rm -f "$PID_FILE"
                break
            fi
            sleep 1
        done

        # 如果进程还在运行，强制杀死
        if ps -p $PID > /dev/null 2>&1; then
            print_warning "进程未响应，强制停止..."
            kill -9 $PID
            rm -f "$PID_FILE"
            print_success "进程已强制停止"
        fi
    else
        print_warning "进程 $PID 不存在"
        rm -f "$PID_FILE"
    fi
else
    print_warning "PID 文件不存在"
fi

# 检查端口是否还被占用
PORT=19001
print_info "检查端口 $PORT..."

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    print_warning "端口 $PORT 仍被占用，尝试停止..."
    PIDS=$(lsof -ti:$PORT)
    for pid in $PIDS; do
        print_info "停止进程 $pid..."
        kill -9 $pid 2>/dev/null || true
    done
    sleep 1
    print_success "端口已释放"
else
    print_success "端口 $PORT 未被占用"
fi

# 清理其他可能的进程
print_info "清理其他相关进程..."
pkill -f "websocket_server.py" 2>/dev/null || true
pkill -f "test_websocket_simple.py" 2>/dev/null || true

echo ""
echo "================================"
print_success "GPU Server 已停止"
