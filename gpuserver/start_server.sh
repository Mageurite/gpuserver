#!/bin/bash
# GPU Server 启动脚本 - 启动 WebSocket 服务器和管理 API

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

print_info "GPU Server 启动脚本"
echo "================================"

# 检查 Python 环境
print_info "检查 Python 环境..."

# 优先使用 conda 环境
if [ -f "/workspace/conda_envs/rag/bin/python" ]; then
    PYTHON_BIN="/workspace/conda_envs/rag/bin/python"
    print_success "使用 conda rag 环境: $PYTHON_BIN"
elif [ -f "/workspace/conda_envs/mt/bin/python" ]; then
    PYTHON_BIN="/workspace/conda_envs/mt/bin/python"
    print_success "使用 conda mt 环境: $PYTHON_BIN"
elif command -v python3 &> /dev/null; then
    PYTHON_BIN="python3"
    print_warning "使用系统 Python3: $PYTHON_BIN"
else
    print_error "未找到 Python 环境！"
    exit 1
fi

# 显示 Python 版本
PYTHON_VERSION=$($PYTHON_BIN --version 2>&1)
print_info "Python 版本: $PYTHON_VERSION"

# 设置环境变量
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
print_info "设置 PYTHONPATH: $PYTHONPATH"

# 检查必需的文件
print_info "检查必需的文件..."
REQUIRED_FILES=(
    "api/websocket_server.py"
    "api/management_api.py"
    "config.py"
    "session_manager.py"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        print_error "缺少必需文件: $file"
        exit 1
    fi
done
print_success "所有必需文件存在"

# 从 .env 读取端口配置
WEBSOCKET_PORT=$(grep WEBSOCKET_PORT .env 2>/dev/null | cut -d '=' -f2)
WEBSOCKET_PORT=${WEBSOCKET_PORT:-9001}  # 默认 9001

MANAGEMENT_PORT=$(grep MANAGEMENT_API_PORT .env 2>/dev/null | cut -d '=' -f2)
MANAGEMENT_PORT=${MANAGEMENT_PORT:-9000}  # 默认 9000

print_info "检查端口是否被占用..."

# 检查 WebSocket 端口
if lsof -Pi :$WEBSOCKET_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    print_warning "WebSocket 端口 $WEBSOCKET_PORT 已被占用"
    read -p "是否停止现有进程并重启？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "停止现有进程..."
        lsof -ti:$WEBSOCKET_PORT | xargs kill -9 2>/dev/null || true
        sleep 2
        print_success "现有进程已停止"
    else
        print_error "端口被占用，无法启动"
        exit 1
    fi
else
    print_success "WebSocket 端口 $WEBSOCKET_PORT 可用"
fi

# 检查管理 API 端口
if lsof -Pi :$MANAGEMENT_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    print_warning "管理 API 端口 $MANAGEMENT_PORT 已被占用"
    lsof -ti:$MANAGEMENT_PORT | xargs kill -9 2>/dev/null || true
    sleep 2
    print_success "管理 API 端口已释放"
else
    print_success "管理 API 端口 $MANAGEMENT_PORT 可用"
fi

# 创建日志目录
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
WEBSOCKET_LOG="$LOG_DIR/websocket_server.log"
MANAGEMENT_LOG="$LOG_DIR/management_api.log"
print_info "日志目录: $LOG_DIR"

# 启动服务器
print_info "启动 GPU Server 服务..."
echo "================================"

# 启动方式选择
if [ "$1" == "--foreground" ] || [ "$1" == "-f" ]; then
    # 前台运行（仅启动 WebSocket 服务器）
    print_info "前台运行模式（仅 WebSocket 服务器）"
    print_warning "管理 API 不会在前台模式启动"
    exec $PYTHON_BIN api/websocket_server.py
else
    # 后台运行两个服务
    print_info "后台运行模式"

    # 1. 启动 WebSocket 服务器
    print_info "启动 WebSocket 服务器 (端口 $WEBSOCKET_PORT)..."
    nohup $PYTHON_BIN api/websocket_server.py > "$WEBSOCKET_LOG" 2>&1 &
    WEBSOCKET_PID=$!
    echo $WEBSOCKET_PID > "$SCRIPT_DIR/websocket_server.pid"
    print_success "WebSocket 服务器已启动 (PID: $WEBSOCKET_PID)"

    # 等待 WebSocket 服务器启动
    sleep 3

    # 检查 WebSocket 服务器是否运行
    if ! ps -p $WEBSOCKET_PID > /dev/null 2>&1; then
        print_error "WebSocket 服务器启动失败！"
        print_info "查看日志: tail -50 $WEBSOCKET_LOG"
        exit 1
    fi

    # 2. 启动管理 API
    print_info "启动管理 API (端口 $MANAGEMENT_PORT)..."
    nohup $PYTHON_BIN api/management_api.py > "$MANAGEMENT_LOG" 2>&1 &
    MANAGEMENT_PID=$!
    echo $MANAGEMENT_PID > "$SCRIPT_DIR/management_api.pid"
    print_success "管理 API 已启动 (PID: $MANAGEMENT_PID)"

    # 等待管理 API 启动
    sleep 3

    # 检查管理 API 是否运行
    if ! ps -p $MANAGEMENT_PID > /dev/null 2>&1; then
        print_error "管理 API 启动失败！"
        print_info "查看日志: tail -50 $MANAGEMENT_LOG"
        exit 1
    fi

    # 测试健康检查
    print_info "测试服务健康状态..."
    sleep 2

    # 检查 WebSocket 服务器
    if command -v curl &> /dev/null; then
        WS_HEALTH=$(curl -s http://localhost:$WEBSOCKET_PORT/health 2>/dev/null || echo "")
        if [ -n "$WS_HEALTH" ]; then
            print_success "WebSocket 服务器健康检查通过"
            echo "$WS_HEALTH" | python3 -m json.tool 2>/dev/null || echo "$WS_HEALTH"
        else
            print_warning "WebSocket 服务器健康检查失败"
        fi

        echo ""

        # 检查管理 API
        MGMT_HEALTH=$(curl -s http://localhost:$MANAGEMENT_PORT/health 2>/dev/null || echo "")
        if [ -n "$MGMT_HEALTH" ]; then
            print_success "管理 API 健康检查通过"
            echo "$MGMT_HEALTH" | python3 -m json.tool 2>/dev/null || echo "$MGMT_HEALTH"
        else
            print_warning "管理 API 健康检查失败"
        fi
    fi

    echo ""
    echo "================================"
    print_success "GPU Server 所有服务启动成功！"
    echo ""
    echo "🚀 服务信息:"
    echo "   ├─ WebSocket 服务器:"
    echo "   │  ├─ PID: $WEBSOCKET_PID"
    echo "   │  ├─ 端口: $WEBSOCKET_PORT"
    echo "   │  ├─ 端点: ws://localhost:$WEBSOCKET_PORT/ws/{connection_id}"
    echo "   │  └─ 日志: $WEBSOCKET_LOG"
    echo "   │"
    echo "   └─ 管理 API:"
    echo "      ├─ PID: $MANAGEMENT_PID"
    echo "      ├─ 端口: $MANAGEMENT_PORT"
    echo "      ├─ 端点: http://localhost:$MANAGEMENT_PORT"
    echo "      └─ 日志: $MANAGEMENT_LOG"
    echo ""
    echo "📊 管理命令:"
    echo "   - 查看 WebSocket 日志: tail -f $WEBSOCKET_LOG"
    echo "   - 查看管理 API 日志: tail -f $MANAGEMENT_LOG"
    echo "   - 停止所有服务: ./stop_server.sh"
    echo "   - 查看进程状态: ps -p $WEBSOCKET_PID,$MANAGEMENT_PID"
    echo ""
    echo "🔍 健康检查:"
    echo "   - WebSocket: curl http://localhost:$WEBSOCKET_PORT/health"
    echo "   - 管理 API: curl http://localhost:$MANAGEMENT_PORT/health"
    echo ""
fi
