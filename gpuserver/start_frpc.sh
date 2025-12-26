#!/bin/bash
#
# GPU Server - frpc 启动脚本（改进版）
# 用途：在 GPU Server 上安全启动 frpc，避免重复启动和配置错误
#

set -e

# 获取脚本所在目录（gpuserver 根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "========================================="
echo "  frpc 启动脚本（改进版）"
echo "========================================="
echo ""

# 1. 检测 frpc 可执行文件
echo -e "${BLUE}[1/5] 检测 frpc...${NC}"
if command -v frpc &> /dev/null; then
    FRPC_BIN=$(which frpc)
elif [ -f "/usr/local/bin/frpc" ]; then
    FRPC_BIN="/usr/local/bin/frpc"
elif [ -f "/usr/local/frp/frpc" ]; then
    FRPC_BIN="/usr/local/frp/frpc"
elif [ -f "$HOME/frp/frpc" ]; then
    FRPC_BIN="$HOME/frp/frpc"
else
    echo -e "${RED}❌ 错误：未找到 frpc${NC}"
    echo "   请先安装 frpc"
    exit 1
fi

echo -e "${GREEN}✅ 找到 frpc: $FRPC_BIN${NC}"
$FRPC_BIN --version
echo ""

# 2. 检测配置文件（优先使用 gpuserver 根目录的配置）
echo -e "${BLUE}[2/5] 检测配置文件...${NC}"
CONFIG_FILE=""
if [ -f "$SCRIPT_DIR/frpc.ini" ]; then
    CONFIG_FILE="$SCRIPT_DIR/frpc.ini"
    echo -e "${GREEN}✅ 找到配置文件: $CONFIG_FILE${NC}"
elif [ -f "$HOME/.frp/frpc.ini" ]; then
    CONFIG_FILE="$HOME/.frp/frpc.ini"
    echo -e "${GREEN}✅ 找到配置文件: $CONFIG_FILE${NC}"
else
    echo -e "${RED}❌ 错误：未找到配置文件 frpc.ini${NC}"
    echo "   请将 frpc.ini 放置在："
    echo "   - $SCRIPT_DIR/frpc.ini （推荐）"
    echo "   - $HOME/.frp/frpc.ini"
    exit 1
fi
echo ""

# 3. 验证配置文件
echo -e "${BLUE}[3/5] 验证配置...${NC}"
SERVER_ADDR=$(grep "^server_addr" "$CONFIG_FILE" | awk '{print $3}' | tr -d '\r')
TOKEN=$(grep "^token" "$CONFIG_FILE" | awk '{print $3}' | tr -d '\r')

if [ -z "$SERVER_ADDR" ]; then
    echo -e "${RED}❌ 错误：配置文件中未找到 server_addr${NC}"
    exit 1
fi

if [ "$SERVER_ADDR" = "YOUR_WEB_SERVER_IP" ]; then
    echo -e "${RED}❌ 错误：server_addr 尚未配置${NC}"
    echo "   请编辑配置文件: $CONFIG_FILE"
    exit 1
fi

echo -e "${GREEN}✅ 配置验证通过${NC}"
echo "   服务器地址: $SERVER_ADDR"
echo "   Token: ${TOKEN:0:8}..."
echo ""

# 4. 检查并清理旧进程
echo -e "${BLUE}[4/5] 检查现有进程...${NC}"
OLD_PIDS=$(pgrep -f "frpc.*\.ini" || true)

if [ -n "$OLD_PIDS" ]; then
    echo -e "${YELLOW}⚠️  发现 frpc 进程正在运行:${NC}"
    ps aux | grep -E "frpc.*\.ini" | grep -v grep || true
    echo ""

    # 非交互模式：自动重启
    if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
        echo "强制模式：停止旧进程..."
        pkill -9 -f "frpc.*\.ini" || true
        sleep 2
    else
        read -p "是否停止并重启？(y/N): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "停止旧进程..."
            pkill -9 -f "frpc.*\.ini" || true
            sleep 2
        else
            echo "取消启动"
            exit 0
        fi
    fi

    # 确认已停止
    if pgrep -f "frpc.*\.ini" > /dev/null; then
        echo -e "${RED}❌ 无法停止旧进程${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ 旧进程已停止${NC}"
else
    echo -e "${GREEN}✅ 无运行中的 frpc 进程${NC}"
fi
echo ""

# 5. 启动 frpc
echo -e "${BLUE}[5/5] 启动 frpc...${NC}"

# 创建日志目录
mkdir -p "$SCRIPT_DIR/logs"
LOG_FILE="$SCRIPT_DIR/logs/frpc_console.log"

# 后台启动
nohup "$FRPC_BIN" -c "$CONFIG_FILE" > "$LOG_FILE" 2>&1 &
FRPC_PID=$!

# 等待启动
sleep 3

# 验证启动
if ps -p $FRPC_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✅ frpc 启动成功！${NC}"
    echo ""
    echo "📊 进程信息："
    echo "   - PID: $FRPC_PID"
    echo "   - 配置文件: $CONFIG_FILE"
    echo "   - 日志文件: $LOG_FILE"
    echo ""

    # 保存 PID
    echo $FRPC_PID > "$SCRIPT_DIR/logs/frpc.pid"

    # 显示最后几行日志
    echo "📝 连接日志（最新）："
    echo "---"
    tail -10 "$SCRIPT_DIR/logs/frpc.log" 2>/dev/null || tail -10 "$LOG_FILE"
    echo "---"
    echo ""

    echo "🔍 查看实时日志："
    echo "   tail -f $SCRIPT_DIR/logs/frpc.log"
    echo ""
    echo "🛑 停止 frpc："
    echo "   kill $FRPC_PID"
    echo "   或: pkill -9 -f 'frpc.*\.ini'"
    echo ""
else
    echo -e "${RED}❌ frpc 启动失败${NC}"
    echo "查看日志: cat $LOG_FILE"
    exit 1
fi

echo "========================================="
echo -e "${GREEN}  frpc 启动完成！${NC}"
echo "========================================="
echo ""
