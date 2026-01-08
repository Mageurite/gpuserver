#!/bin/bash
# GPU Server 启动脚本

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

# 从 .env 读取 WebSocket 端口
PORT=$(grep WEBSOCKET_PORT .env | cut -d '=' -f2)
PORT=${PORT:-9001}  # 如果未设置，默认使用 9001

print_info "检查端口 $PORT 是否被占用..."
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    print_warning "端口 $PORT 已被占用"
    read -p "是否停止现有进程并重启？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "停止现有进程..."
        lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
        sleep 2
        print_success "现有进程已停止"
    else
        print_error "端口被占用，无法启动"
        exit 1
    fi
else
    print_success "端口 $PORT 可用"
fi

# 创建日志目录
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/websocket_server.log"
print_info "日志文件: $LOG_FILE"

# 启动服务器
print_info "启动 GPU Server..."
echo "================================"

# 启动方式选择
if [ "$1" == "--foreground" ] || [ "$1" == "-f" ]; then
    # 前台运行
    print_info "前台运行模式"
    exec $PYTHON_BIN api/websocket_server.py
else
    # 后台运行
    print_info "后台运行模式"
    nohup $PYTHON_BIN api/websocket_server.py > "$LOG_FILE" 2>&1 &
    PID=$!

    # 保存 PID
    echo $PID > "$SCRIPT_DIR/websocket_server.pid"

    print_success "GPU Server 已启动 (PID: $PID)"
    print_info "日志文件: $LOG_FILE"

    # 等待服务器启动
    print_info "等待服务器启动..."
    sleep 3

    # 检查进程是否还在运行
    if ps -p $PID > /dev/null 2>&1; then
        print_success "GPU Server 运行正常"

        # 测试健康检查
        print_info "测试健康检查接口..."
        if command -v curl &> /dev/null; then
            sleep 2
            HEALTH_CHECK=$(curl -s http://localhost:$PORT/health 2>/dev/null || echo "")
            if [ -n "$HEALTH_CHECK" ]; then
                print_success "健康检查通过"
                echo "$HEALTH_CHECK" | python3 -m json.tool 2>/dev/null || echo "$HEALTH_CHECK"
            else
                print_warning "健康检查失败，请查看日志"
            fi
        fi

        echo ""
        echo "================================"
        print_success "GPU Server 启动成功！"
        echo ""
        echo "📍 WebSocket 端点:"
        echo "   - ws://localhost:$PORT/ws/{connection_id}"
        echo "   - ws://localhost:$PORT/ws/ws/{connection_id}"
        echo ""
        echo "📊 管理命令:"
        echo "   - 查看日志: tail -f $LOG_FILE"
        echo "   - 停止服务: ./stop_server.sh"
        echo "   - 查看状态: ps -p $PID"
        echo ""
    else
        print_error "GPU Server 启动失败！"
        print_info "查看日志获取详细信息:"
        echo "   tail -50 $LOG_FILE"
        exit 1
    fi
fi
