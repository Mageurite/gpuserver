#!/bin/bash
# GPU Server 启动脚本（统一模式）
# 启动集成的管理 API 和 WebSocket 服务

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=========================================="
echo "  GPU Server - 启动服务"
echo "=========================================="
echo ""

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}警告: .env 文件不存在，正在从 .env.example 复制...${NC}"
    cp .env.example .env
    echo -e "${GREEN}已创建 .env 文件，请根据需要修改配置${NC}"
fi

# 检查是否已经在运行
if pgrep -f "python.*unified_server.py" > /dev/null; then
    echo -e "${YELLOW}GPU Server 已在运行中${NC}"
    echo "请先停止现有服务: ./stop.sh"
    exit 1
fi

# 检查 Python 环境
echo "检查 Python 环境..."
if [ -d "/workspace/conda_envs/rag/bin" ]; then
    export PATH="/workspace/conda_envs/rag/bin:$PATH"
    PYTHON_CMD="/workspace/conda_envs/rag/bin/python"
    echo -e "${GREEN}使用 conda 环境: /workspace/conda_envs/rag${NC}"
else
    PYTHON_CMD="python3"
    echo -e "${YELLOW}使用系统 Python${NC}"
fi

# 检查 Python 是否可用
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo -e "${RED}错误: Python 未找到${NC}"
    exit 1
fi

# 检查必要的依赖
echo "检查依赖..."
if ! $PYTHON_CMD -c "import fastapi, uvicorn, websockets" 2>/dev/null; then
    echo -e "${YELLOW}警告: 缺少必要的 Python 包，正在安装...${NC}"
    pip install -r requirements.txt
fi

# 加载环境变量
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# 设置默认端口
MANAGEMENT_API_PORT=${MANAGEMENT_API_PORT:-9000}

echo ""
echo "正在启动 GPU Server..."
echo "  - 管理 API: http://0.0.0.0:${MANAGEMENT_API_PORT}/mgmt"
echo "  - 管理 API (兼容): http://0.0.0.0:${MANAGEMENT_API_PORT}/v1/sessions"
echo "  - WebSocket: ws://0.0.0.0:${MANAGEMENT_API_PORT}/ws/ws/{session_id}"
echo "  - API 文档: http://0.0.0.0:${MANAGEMENT_API_PORT}/docs"
echo ""

# 启动服务
nohup $PYTHON_CMD unified_server.py > logs/server.log 2>&1 &
SERVER_PID=$!

# 等待服务启动
echo "等待服务启动..."
sleep 3

# 检查服务是否成功启动
if ps -p $SERVER_PID > /dev/null; then
    echo -e "${GREEN}✓ GPU Server 启动成功 (PID: $SERVER_PID)${NC}"
    echo ""
    echo "查看日志: tail -f logs/server.log"
    echo "停止服务: ./stop.sh"
    echo "健康检查: curl http://localhost:${MANAGEMENT_API_PORT}/health"
    echo ""

    # 保存 PID
    mkdir -p logs
    echo $SERVER_PID > logs/server.pid

    # 尝试健康检查
    sleep 2
    if curl -s http://localhost:${MANAGEMENT_API_PORT}/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 健康检查通过${NC}"
    else
        echo -e "${YELLOW}! 健康检查失败，请查看日志${NC}"
    fi
else
    echo -e "${RED}✗ GPU Server 启动失败${NC}"
    echo "请查看日志: cat logs/server.log"
    exit 1
fi

echo ""
echo "=========================================="
