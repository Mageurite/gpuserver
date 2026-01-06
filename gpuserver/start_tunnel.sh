#!/bin/bash
# SSH 反向隧道启动脚本
# 用于替代 FRP，建立 GPU Server 到 Web Server 的反向隧道

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

print_info "SSH 反向隧道启动脚本"
echo "========================================"

# 创建日志目录
mkdir -p "$LOG_DIR"
mkdir -p "$PID_DIR"

# 检查 SSH 是否可用
if ! command -v ssh &> /dev/null; then
    print_error "未找到 ssh 命令，请安装 openssh-client"
    exit 1
fi

# 检查 autossh 是否可用（推荐但不强制）
USE_AUTOSSH=false
if command -v autossh &> /dev/null; then
    USE_AUTOSSH=true
    print_success "找到 autossh，将使用自动重连功能"
else
    print_warning "未找到 autossh，建议安装: apt-get install autossh"
    print_info "将使用普通 SSH（无自动重连）"
fi

# 检查 SSH 密钥
if [ -n "$SSH_KEY_PATH" ] && [ -f "$SSH_KEY_PATH" ]; then
    SSH_KEY_ARG="-i $SSH_KEY_PATH"
    print_success "使用 SSH 密钥: $SSH_KEY_PATH"
else
    SSH_KEY_ARG=""
    print_warning "未配置 SSH 密钥，将使用密码认证"
fi

# 检查是否已有隧道在运行
if [ -f "$TUNNEL_PID" ]; then
    OLD_PID=$(cat "$TUNNEL_PID")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        print_warning "发现已运行的隧道 (PID: $OLD_PID)"
        read -p "是否停止现有隧道并重启？(y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "停止现有隧道..."
            kill "$OLD_PID" 2>/dev/null || true
            sleep 2
            print_success "现有隧道已停止"
        else
            print_error "取消启动"
            exit 1
        fi
    fi
    rm -f "$TUNNEL_PID"
fi

# 测试 SSH 连接
print_info "测试 SSH 连接..."
if ssh $SSH_KEY_ARG \
    -o ConnectTimeout=10 \
    -o StrictHostKeyChecking=no \
    -p "$WEBSERVER_SSH_PORT" \
    "${WEBSERVER_USER}@${WEBSERVER_HOST}" \
    "echo 'SSH 连接测试成功'" 2>&1 | tee -a "$TUNNEL_LOG"; then
    print_success "SSH 连接测试成功"
else
    print_error "SSH 连接失败，请检查："
    echo "  1. Web Server 地址和端口是否正确"
    echo "  2. SSH 密钥或密码是否正确"
    echo "  3. 网络连接是否正常"
    exit 1
fi

# 构建 SSH 参数
SSH_OPTS=(
    -N  # 不执行远程命令
    -T  # 禁用伪终端分配
    -o ServerAliveInterval=$KEEPALIVE_INTERVAL
    -o ServerAliveCountMax=3
    -o ExitOnForwardFailure=yes
    -o StrictHostKeyChecking=no
    -p "$WEBSERVER_SSH_PORT"
)

if [ -n "$SSH_KEY_ARG" ]; then
    SSH_OPTS+=($SSH_KEY_ARG)
fi

# 端口转发配置
SSH_OPTS+=(
    -R "${REMOTE_MGMT_PORT}:127.0.0.1:${LOCAL_MGMT_PORT}"
    -R "${REMOTE_WS_PORT}:127.0.0.1:${LOCAL_WS_PORT}"
)

# 启动隧道
print_info "启动 SSH 反向隧道..."
echo "----------------------------------------"
echo "Management API: 127.0.0.1:${LOCAL_MGMT_PORT} -> ${WEBSERVER_HOST}:${REMOTE_MGMT_PORT}"
echo "WebSocket:      127.0.0.1:${LOCAL_WS_PORT} -> ${WEBSERVER_HOST}:${REMOTE_WS_PORT}"
echo "----------------------------------------"

if [ "$USE_AUTOSSH" = true ]; then
    # 使用 autossh（支持自动重连）
    export AUTOSSH_PIDFILE="$TUNNEL_PID"
    export AUTOSSH_POLL=60
    export AUTOSSH_FIRST_POLL=30
    export AUTOSSH_GATETIME=0
    export AUTOSSH_LOGFILE="$TUNNEL_LOG"
    
    autossh -M 0 -f \
        "${SSH_OPTS[@]}" \
        "${WEBSERVER_USER}@${WEBSERVER_HOST}" \
        >> "$TUNNEL_LOG" 2>&1
    
    # 等待 PID 文件生成
    sleep 2
    if [ -f "$TUNNEL_PID" ]; then
        TUNNEL_PID_NUM=$(cat "$TUNNEL_PID")
        print_success "SSH 反向隧道已启动 (PID: $TUNNEL_PID_NUM)"
        print_info "使用 autossh，支持自动重连"
    else
        print_error "启动失败，请查看日志: $TUNNEL_LOG"
        exit 1
    fi
else
    # 使用普通 SSH（后台运行）
    ssh -f \
        "${SSH_OPTS[@]}" \
        "${WEBSERVER_USER}@${WEBSERVER_HOST}" \
        >> "$TUNNEL_LOG" 2>&1
    
    # 获取 SSH 进程 PID
    sleep 2
    SSH_PID=$(pgrep -f "ssh.*${WEBSERVER_HOST}.*${REMOTE_MGMT_PORT}" | head -n 1)
    if [ -n "$SSH_PID" ]; then
        echo "$SSH_PID" > "$TUNNEL_PID"
        print_success "SSH 反向隧道已启动 (PID: $SSH_PID)"
        print_warning "使用普通 SSH，不支持自动重连"
    else
        print_error "启动失败，请查看日志: $TUNNEL_LOG"
        exit 1
    fi
fi

echo "========================================"
print_success "反向隧道启动完成！"
echo ""
print_info "管理命令："
echo "  查看状态: ./status_tunnel.sh"
echo "  停止隧道: ./stop_tunnel.sh"
echo "  查看日志: tail -f $TUNNEL_LOG"
echo ""
print_info "Web Server 可通过以下地址访问 GPU Server："
echo "  Management API: http://localhost:${REMOTE_MGMT_PORT}"
echo "  WebSocket:      ws://localhost:${REMOTE_WS_PORT}"
