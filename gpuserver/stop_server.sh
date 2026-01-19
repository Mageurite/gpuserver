#!/bin/bash
# GPU Server 停止脚本 - 停止 WebSocket 服务器和管理 API

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

# 停止函数
stop_service() {
    local SERVICE_NAME=$1
    local PID_FILE=$2
    local PROCESS_NAME=$3

    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        print_info "[$SERVICE_NAME] 从 PID 文件读取: $PID"

        # 检查进程是否存在
        if ps -p $PID > /dev/null 2>&1; then
            print_info "[$SERVICE_NAME] 停止进程 $PID..."
            kill $PID

            # 等待进程结束
            for i in {1..10}; do
                if ! ps -p $PID > /dev/null 2>&1; then
                    print_success "[$SERVICE_NAME] 进程已停止"
                    rm -f "$PID_FILE"
                    return 0
                fi
                sleep 1
            done

            # 如果进程还在运行，强制杀死
            if ps -p $PID > /dev/null 2>&1; then
                print_warning "[$SERVICE_NAME] 进程未响应，强制停止..."
                kill -9 $PID
                rm -f "$PID_FILE"
                print_success "[$SERVICE_NAME] 进程已强制停止"
            fi
        else
            print_warning "[$SERVICE_NAME] 进程 $PID 不存在"
            rm -f "$PID_FILE"
        fi
    else
        print_warning "[$SERVICE_NAME] PID 文件不存在: $PID_FILE"
        # 尝试通过进程名查找
        PIDS=$(pgrep -f "$PROCESS_NAME" 2>/dev/null || echo "")
        if [ -n "$PIDS" ]; then
            print_info "[$SERVICE_NAME] 通过进程名找到: $PIDS"
            for pid in $PIDS; do
                print_info "[$SERVICE_NAME] 停止进程 $pid..."
                kill -9 $pid 2>/dev/null || true
            done
            print_success "[$SERVICE_NAME] 进程已停止"
        fi
    fi
}

# 1. 停止 WebSocket 服务器
stop_service "WebSocket" "$SCRIPT_DIR/websocket_server.pid" "api/websocket_server.py"

# 2. 停止管理 API
stop_service "管理 API" "$SCRIPT_DIR/management_api.pid" "api/management_api.py"

# 检查端口是否还被占用
WEBSOCKET_PORT=$(grep WEBSOCKET_PORT .env 2>/dev/null | cut -d '=' -f2)
WEBSOCKET_PORT=${WEBSOCKET_PORT:-9001}

MANAGEMENT_PORT=$(grep MANAGEMENT_API_PORT .env 2>/dev/null | cut -d '=' -f2)
MANAGEMENT_PORT=${MANAGEMENT_PORT:-9000}

print_info "检查端口占用情况..."

# 检查 WebSocket 端口
if lsof -Pi :$WEBSOCKET_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    print_warning "WebSocket 端口 $WEBSOCKET_PORT 仍被占用，尝试释放..."
    PIDS=$(lsof -ti:$WEBSOCKET_PORT)
    for pid in $PIDS; do
        print_info "停止进程 $pid..."
        kill -9 $pid 2>/dev/null || true
    done
    sleep 1
    print_success "WebSocket 端口已释放"
else
    print_success "WebSocket 端口 $WEBSOCKET_PORT 未被占用"
fi

# 检查管理 API 端口
if lsof -Pi :$MANAGEMENT_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    print_warning "管理 API 端口 $MANAGEMENT_PORT 仍被占用，尝试释放..."
    PIDS=$(lsof -ti:$MANAGEMENT_PORT)
    for pid in $PIDS; do
        print_info "停止进程 $pid..."
        kill -9 $pid 2>/dev/null || true
    done
    sleep 1
    print_success "管理 API 端口已释放"
else
    print_success "管理 API 端口 $MANAGEMENT_PORT 未被占用"
fi

# 检查并释放 WebRTC UDP 端口 (10110-10115)
print_info "检查 WebRTC UDP 端口 (10110-10115)..."
RELEASED_PORTS=0
for port in {10110..10115}; do
    # 检查端口是否被占用（排除 turnserver）
    PIDS=$(ss -tulnp | grep ":$port" | grep -v turnserver | awk '{print $7}' | cut -d',' -f2 | cut -d'=' -f2 | sort -u)

    if [ -n "$PIDS" ]; then
        print_warning "端口 $port 被占用，尝试释放..."
        for pid in $PIDS; do
            if [ -n "$pid" ] && [ "$pid" != "-" ]; then
                print_info "停止占用端口 $port 的进程: $pid"
                kill -9 $pid 2>/dev/null || true
                RELEASED_PORTS=$((RELEASED_PORTS + 1))
            fi
        done
    fi
done

if [ $RELEASED_PORTS -gt 0 ]; then
    print_success "已释放 $RELEASED_PORTS 个 WebRTC 端口"
else
    print_success "WebRTC 端口 (10110-10115) 未被占用或仅被 TURN 服务器占用"
fi

# 清理其他可能的进程
print_info "清理其他相关进程..."
pkill -f "websocket_server.py" 2>/dev/null || true
pkill -f "management_api.py" 2>/dev/null || true
pkill -f "test_websocket_simple.py" 2>/dev/null || true

echo ""
echo "================================"
print_success "GPU Server 所有服务已停止"
echo ""
echo "✅ 已停止服务:"
echo "   ├─ WebSocket 服务器 (端口 $WEBSOCKET_PORT)"
echo "   ├─ 管理 API (端口 $MANAGEMENT_PORT)"
echo "   └─ WebRTC 端口 (10110-10115) 已检查"
echo ""
echo "💡 提示:"
echo "   - TURN 服务器 (端口 10110) 保持运行"
echo "   - 如需重启 TURN: sudo systemctl restart coturn 或 kill <turnserver-pid>"
echo ""
