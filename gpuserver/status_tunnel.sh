#!/bin/bash
# SSH 反向隧道状态检查脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 加载配置
if [ ! -f "tunnel_config.sh" ]; then
    print_error "未找到配置文件: tunnel_config.sh"
    exit 1
fi
source tunnel_config.sh

echo "========================================"
echo "SSH 反向隧道状态"
echo "========================================"

# 检查 PID 文件
if [ ! -f "$TUNNEL_PID" ]; then
    print_error "隧道未运行 (未找到 PID 文件)"
    echo ""
    print_info "启动隧道: ./start_tunnel.sh"
    exit 1
fi

# 读取 PID
TUNNEL_PID_NUM=$(cat "$TUNNEL_PID")

# 检查进程是否存在
if ! ps -p "$TUNNEL_PID_NUM" > /dev/null 2>&1; then
    print_error "隧道未运行 (进程 $TUNNEL_PID_NUM 不存在)"
    rm -f "$TUNNEL_PID"
    echo ""
    print_info "启动隧道: ./start_tunnel.sh"
    exit 1
fi

# 显示进程信息
print_success "隧道正在运行 (PID: $TUNNEL_PID_NUM)"
echo ""
echo "进程信息:"
ps -f -p "$TUNNEL_PID_NUM" || true
echo ""

# 显示配置信息
echo "配置信息:"
echo "  Web Server: ${WEBSERVER_USER}@${WEBSERVER_HOST}:${WEBSERVER_SSH_PORT}"
echo ""
echo "端口映射:"
echo "  Management API: 127.0.0.1:${LOCAL_MGMT_PORT} -> ${WEBSERVER_HOST}:${REMOTE_MGMT_PORT}"
echo "  WebSocket:      127.0.0.1:${LOCAL_WS_PORT} -> ${WEBSERVER_HOST}:${REMOTE_WS_PORT}"
echo ""

# 显示连接统计
echo "运行时间:"
ps -o etime= -p "$TUNNEL_PID_NUM" 2>/dev/null || echo "  未知"
echo ""

# 显示最近的日志
if [ -f "$TUNNEL_LOG" ]; then
    echo "最近日志 (最后 10 行):"
    echo "----------------------------------------"
    tail -n 10 "$TUNNEL_LOG" 2>/dev/null || echo "  无日志内容"
    echo "----------------------------------------"
    echo ""
    print_info "完整日志: tail -f $TUNNEL_LOG"
fi

echo "========================================"
print_success "隧道状态检查完成"
echo ""
print_info "管理命令："
echo "  停止隧道: ./stop_tunnel.sh"
echo "  重启隧道: ./stop_tunnel.sh && ./start_tunnel.sh"
