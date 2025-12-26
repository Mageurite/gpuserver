#!/bin/bash
#
# GPU Server 一键启动脚本
# 启动 GPU Server 和 FRP（如果配置了）
#

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "  Virtual Tutor GPU Server"
echo "  一键启动脚本"
echo "=========================================="
echo ""

# 1. 检查环境
echo -e "${BLUE}[1/4] 检查环境...${NC}"

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}警告: .env 文件不存在，正在从 .env.example 复制...${NC}"
    cp .env.example .env
    echo -e "${GREEN}已创建 .env 文件${NC}"
fi

# 加载环境变量
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs -0)
fi

# 检查是否已经在运行
if pgrep -f "python.*unified_server.py" > /dev/null; then
    echo -e "${YELLOW}GPU Server 已在运行中${NC}"
    read -p "是否重启服务？(y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "正在停止现有服务..."
        ./stop.sh
        sleep 2
    else
        echo "退出启动"
        exit 0
    fi
fi

echo -e "${GREEN}✓ 环境检查完成${NC}"
echo ""

# 2. 启动 FRP（可选）
echo -e "${BLUE}[2/4] 检查 FRP 配置...${NC}"

START_FRP=false
if [ -f ".env.frp" ]; then
    echo -e "${GREEN}找到 FRP 配置文件 (.env.frp)${NC}"

    # 询问是否启动 FRP
    read -p "是否启动 FRP 内网穿透？(Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        START_FRP=true
    fi
elif [ -f "frpc.ini" ]; then
    echo -e "${GREEN}找到 FRP 配置文件 (frpc.ini)${NC}"
    read -p "是否启动 FRP 内网穿透？(Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        START_FRP=true
    fi
else
    echo -e "${YELLOW}未找到 FRP 配置，跳过 FRP 启动${NC}"
    echo "  (如需使用 FRP，请配置 .env.frp 或 frpc.ini)"
fi

if [ "$START_FRP" = true ]; then
    echo "正在启动 FRP..."
    if [ -f "start_frpc.sh" ]; then
        bash start_frpc.sh --force
    elif [ -f "temp/scripts/start_frpc.sh" ]; then
        bash temp/scripts/start_frpc.sh
    else
        echo -e "${YELLOW}找不到 FRP 启动脚本，跳过${NC}"
    fi
fi

echo ""

# 3. 启动 GPU Server
echo -e "${BLUE}[3/4] 启动 GPU Server...${NC}"

# 检查 Python 环境
if [ -d "/workspace/conda_envs/rag/bin" ]; then
    export PATH="/workspace/conda_envs/rag/bin:$PATH"
    PYTHON_CMD="/workspace/conda_envs/rag/bin/python"
    echo -e "${GREEN}使用 conda 环境: /workspace/conda_envs/rag${NC}"
else
    PYTHON_CMD="python3"
    echo -e "${YELLOW}使用系统 Python${NC}"
fi

# 创建日志目录
mkdir -p logs

# 启动服务
MANAGEMENT_API_PORT=${MANAGEMENT_API_PORT:-9000}
nohup $PYTHON_CMD unified_server.py > logs/unified_server.log 2>&1 &
SERVER_PID=$!

echo "等待服务启动..."
sleep 3

# 检查服务是否成功启动
if ps -p $SERVER_PID > /dev/null; then
    echo -e "${GREEN}✓ GPU Server 启动成功 (PID: $SERVER_PID)${NC}"
    echo $SERVER_PID > logs/server.pid
else
    echo -e "${RED}✗ GPU Server 启动失败${NC}"
    echo "请查看日志: tail -f logs/unified_server.log"
    exit 1
fi

echo ""

# 4. 健康检查
echo -e "${BLUE}[4/4] 健康检查...${NC}"

sleep 2
if curl -s http://localhost:${MANAGEMENT_API_PORT}/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 健康检查通过${NC}"

    # 获取健康检查详情
    HEALTH_INFO=$(curl -s http://localhost:${MANAGEMENT_API_PORT}/health)
    echo "  服务状态: $(echo $HEALTH_INFO | grep -o '"status":"[^"]*"' | cut -d'"' -f4)"
else
    echo -e "${YELLOW}! 健康检查失败，请查看日志${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}  GPU Server 启动完成！${NC}"
echo "=========================================="
echo ""
echo "📊 服务信息："
echo "  - 管理 API: http://localhost:${MANAGEMENT_API_PORT}/mgmt"
echo "  - WebSocket: ws://localhost:${MANAGEMENT_API_PORT}/ws/ws/{session_id}"
echo "  - API 文档: http://localhost:${MANAGEMENT_API_PORT}/docs"
echo ""

if [ "$START_FRP" = true ]; then
    # 从 .env 读取 WEBSOCKET_URL 来显示公网地址
    if [ ! -z "$WEBSOCKET_URL" ]; then
        PUBLIC_HOST=$(echo $WEBSOCKET_URL | sed -E 's|ws://([^:]+):.*|\1|')
        PUBLIC_PORT=$(echo $WEBSOCKET_URL | sed -E 's|ws://[^:]+:([0-9]+).*|\1|')
        echo "🌐 通过 FRP 访问（公网）："
        echo "  - WebSocket: ws://${PUBLIC_HOST}:${PUBLIC_PORT}/ws/ws/{session_id}"
        echo ""
    fi
fi

echo "📝 查看日志:"
echo "  tail -f logs/unified_server.log"
echo ""
echo "🛑 停止服务:"
echo "  ./stop.sh"
echo ""
echo "🔄 重启服务:"
echo "  ./restart.sh"
echo ""
echo "=========================================="
