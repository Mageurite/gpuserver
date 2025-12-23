#!/bin/bash
# GPU Server 状态查询脚本
# 显示服务运行状态、端口占用、资源使用等信息

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
echo "  GPU Server - 服务状态"
echo "=========================================="
echo ""

# 检查服务是否运行
echo -e "${BLUE}[1] 进程状态${NC}"
if pgrep -f "python.*unified_server.py" > /dev/null; then
    PID=$(pgrep -f "python.*unified_server.py")
    echo -e "${GREEN}✓ GPU Server 正在运行${NC}"
    echo "  PID: $PID"

    # 显示进程详细信息
    echo "  命令: $(ps -p $PID -o command=)"

    # 显示运行时长
    UPTIME=$(ps -p $PID -o etime= | tr -d ' ')
    echo "  运行时长: $UPTIME"

    # 显示内存使用
    MEM=$(ps -p $PID -o rss= | awk '{printf "%.2f MB", $1/1024}')
    echo "  内存使用: $MEM"

    # 显示 CPU 使用
    CPU=$(ps -p $PID -o %cpu= | tr -d ' ')
    echo "  CPU 使用: ${CPU}%"
else
    echo -e "${RED}✗ GPU Server 未运行${NC}"
fi

echo ""

# 检查 PID 文件
echo -e "${BLUE}[2] PID 文件${NC}"
if [ -f "logs/server.pid" ]; then
    SAVED_PID=$(cat logs/server.pid)
    echo -e "${GREEN}✓ PID 文件存在${NC}"
    echo "  保存的 PID: $SAVED_PID"

    # 检查 PID 是否有效
    if ps -p $SAVED_PID > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓ 进程有效${NC}"
    else
        echo -e "  ${RED}✗ 进程不存在（可能是脏数据）${NC}"
    fi
else
    echo -e "${YELLOW}! PID 文件不存在${NC}"
fi

echo ""

# 检查端口占用
echo -e "${BLUE}[3] 端口状态${NC}"
PORT=${MANAGEMENT_API_PORT:-9000}

if command -v lsof &> /dev/null; then
    if lsof -i :$PORT > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 端口 $PORT 正在使用${NC}"
        lsof -i :$PORT | grep LISTEN | awk '{print "  PID: "$2", 进程: "$1}'
    else
        echo -e "${YELLOW}! 端口 $PORT 未被占用${NC}"
    fi
elif command -v netstat &> /dev/null; then
    if netstat -tln | grep ":$PORT " > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 端口 $PORT 正在使用${NC}"
    else
        echo -e "${YELLOW}! 端口 $PORT 未被占用${NC}"
    fi
else
    echo -e "${YELLOW}! 无法检查端口（lsof 和 netstat 都不可用）${NC}"
fi

echo ""

# 健康检查
echo -e "${BLUE}[4] 健康检查${NC}"
if command -v curl &> /dev/null; then
    HEALTH_RESPONSE=$(curl -s http://localhost:$PORT/health 2>&1)

    if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
        echo -e "${GREEN}✓ 健康检查通过${NC}"
        echo "  响应: $HEALTH_RESPONSE"
    else
        echo -e "${RED}✗ 健康检查失败${NC}"
        echo "  错误: $HEALTH_RESPONSE"
    fi
else
    echo -e "${YELLOW}! curl 未安装，跳过健康检查${NC}"
fi

echo ""

# 检查日志文件
echo -e "${BLUE}[5] 日志文件${NC}"
if [ -f "logs/server.log" ]; then
    LOG_SIZE=$(du -h logs/server.log | cut -f1)
    LOG_LINES=$(wc -l < logs/server.log)
    echo -e "${GREEN}✓ 日志文件存在${NC}"
    echo "  路径: logs/server.log"
    echo "  大小: $LOG_SIZE"
    echo "  行数: $LOG_LINES"

    # 显示最后 5 行日志
    echo ""
    echo "  最后 5 行日志:"
    tail -n 5 logs/server.log | sed 's/^/    /'
else
    echo -e "${YELLOW}! 日志文件不存在${NC}"
fi

echo ""

# 检查配置文件
echo -e "${BLUE}[6] 配置文件${NC}"
if [ -f ".env" ]; then
    echo -e "${GREEN}✓ .env 文件存在${NC}"

    # 显示关键配置（不显示敏感信息）
    if grep -q "MANAGEMENT_API_PORT" .env; then
        PORT_CONFIG=$(grep "MANAGEMENT_API_PORT" .env | cut -d'=' -f2)
        echo "  端口配置: $PORT_CONFIG"
    fi

    if grep -q "MAX_SESSIONS" .env; then
        MAX_SESSIONS=$(grep "MAX_SESSIONS" .env | cut -d'=' -f2)
        echo "  最大会话数: $MAX_SESSIONS"
    fi

    if grep -q "ENABLE_LLM" .env; then
        ENABLE_LLM=$(grep "ENABLE_LLM" .env | cut -d'=' -f2)
        echo "  LLM 启用: $ENABLE_LLM"
    fi
else
    echo -e "${YELLOW}! .env 文件不存在${NC}"
fi

echo ""

# 显示访问地址
echo -e "${BLUE}[7] 访问地址${NC}"
if pgrep -f "python.*unified_server.py" > /dev/null; then
    echo "  管理 API: http://localhost:$PORT/mgmt"
    echo "  管理 API (兼容): http://localhost:$PORT/v1/sessions"
    echo "  WebSocket: ws://localhost:$PORT/ws/ws/{session_id}"
    echo "  API 文档: http://localhost:$PORT/docs"
    echo "  健康检查: curl http://localhost:$PORT/health"
else
    echo -e "${YELLOW}  服务未运行，无法访问${NC}"
fi

echo ""

# 显示快速操作
echo -e "${BLUE}[8] 快速操作${NC}"
echo "  启动服务: ./start.sh"
echo "  停止服务: ./stop.sh"
echo "  重启服务: ./restart.sh"
echo "  查看日志: tail -f logs/server.log"
echo "  查看状态: ./status.sh"

echo ""
echo "=========================================="
echo ""
