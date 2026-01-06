#!/bin/bash
# SSH 反向隧道停止脚本

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

print_info "SSH 反向隧道停止脚本"
echo "========================================"

# 检查 PID 文件
if [ ! -f "$TUNNEL_PID" ]; then
    print_warning "未找到 PID 文件，隧道可能未运行"
    
    # 尝试查找相关进程
    print_info "尝试查找 SSH 隧道进程..."
    SSH_PROCS=$(pgrep -f "ssh.*${WEBSERVER_HOST}.*${REMOTE_MGMT_PORT}" || true)
    
    if [ -n "$SSH_PROCS" ]; then
        print_warning "找到以下可能的隧道进程："
        ps -f -p $SSH_PROCS
        read -p "是否停止这些进程？(y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "$SSH_PROCS" | xargs kill 2>/dev/null || true
            sleep 1
            print_success "进程已停止"
        fi
    else
        print_info "未找到运行中的隧道进程"
    fi
    exit 0
fi

# 读取 PID
TUNNEL_PID_NUM=$(cat "$TUNNEL_PID")
print_info "找到隧道进程 PID: $TUNNEL_PID_NUM"

# 检查进程是否存在
if ! ps -p "$TUNNEL_PID_NUM" > /dev/null 2>&1; then
    print_warning "进程 $TUNNEL_PID_NUM 不存在"
    rm -f "$TUNNEL_PID"
    print_info "已清理 PID 文件"
    exit 0
fi

# 停止进程
print_info "正在停止隧道进程..."
kill "$TUNNEL_PID_NUM" 2>/dev/null || true

# 等待进程结束
for i in {1..10}; do
    if ! ps -p "$TUNNEL_PID_NUM" > /dev/null 2>&1; then
        print_success "隧道已停止"
        rm -f "$TUNNEL_PID"
        echo "========================================"
        exit 0
    fi
    sleep 1
done

# 强制停止
print_warning "进程未响应，尝试强制停止..."
kill -9 "$TUNNEL_PID_NUM" 2>/dev/null || true
sleep 1

if ! ps -p "$TUNNEL_PID_NUM" > /dev/null 2>&1; then
    print_success "隧道已强制停止"
    rm -f "$TUNNEL_PID"
else
    print_error "无法停止进程 $TUNNEL_PID_NUM"
    exit 1
fi

echo "========================================"
