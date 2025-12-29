#!/bin/bash
# GPU Server 状态查看脚本

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

echo "================================"
print_info "GPU Server 状态"
echo "================================"
echo ""

# 检查 PID 文件
PID_FILE="$SCRIPT_DIR/websocket_server.pid"
PORT=19001

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    print_info "PID 文件: $PID"

    # 检查进程是否存在
    if ps -p $PID > /dev/null 2>&1; then
        print_success "进程运行中 (PID: $PID)"

        # 显示进程信息
        echo ""
        print_info "进程详情:"
        ps -p $PID -o pid,ppid,cmd,%cpu,%mem,etime
    else
        print_error "进程不存在 (PID: $PID)"
        print_warning "PID 文件可能过期"
    fi
else
    print_warning "PID 文件不存在"
fi

echo ""

# 检查端口
print_info "端口状态 ($PORT):"
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    print_success "端口 $PORT 正在监听"
    echo ""
    lsof -Pi :$PORT -sTCP:LISTEN
else
    print_error "端口 $PORT 未被监听"
fi

echo ""

# 测试健康检查
print_info "健康检查:"
if command -v curl &> /dev/null; then
    HEALTH_CHECK=$(curl -s http://localhost:$PORT/health 2>/dev/null || echo "")
    if [ -n "$HEALTH_CHECK" ]; then
        print_success "健康检查通过"
        echo "$HEALTH_CHECK" | python3 -m json.tool 2>/dev/null || echo "$HEALTH_CHECK"
    else
        print_error "健康检查失败"
    fi
else
    print_warning "curl 未安装，跳过健康检查"
fi

echo ""

# 显示日志文件
LOG_FILE="$SCRIPT_DIR/logs/websocket_server.log"
if [ -f "$LOG_FILE" ]; then
    print_info "最近日志 (最后 20 行):"
    echo "================================"
    tail -20 "$LOG_FILE"
    echo "================================"
    echo ""
    print_info "完整日志: $LOG_FILE"
else
    print_warning "日志文件不存在: $LOG_FILE"
fi

echo ""

# 显示管理命令
print_info "管理命令:"
echo "  启动服务: ./start_server.sh"
echo "  停止服务: ./stop_server.sh"
echo "  查看日志: tail -f $LOG_FILE"
echo "  重启服务: ./stop_server.sh && ./start_server.sh"
echo ""
