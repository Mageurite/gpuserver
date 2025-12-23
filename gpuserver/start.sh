#!/bin/bash
#
# GPU Server 启动脚本
# 启动管理 API (Port 9000) 和 WebSocket 服务 (Port 9001)
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志目录
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# PID 文件
PID_FILE_MGMT="$LOG_DIR/management_api.pid"
PID_FILE_WS="$LOG_DIR/websocket_server.pid"

echo -e "${GREEN}=== Starting GPU Server ===${NC}"

# 检查是否已经在运行
if [ -f "$PID_FILE_MGMT" ] && kill -0 $(cat "$PID_FILE_MGMT") 2>/dev/null; then
    echo -e "${YELLOW}Management API is already running (PID: $(cat $PID_FILE_MGMT))${NC}"
else
    # 启动管理 API
    echo -e "${GREEN}Starting Management API on port 9000...${NC}"
    nohup python3 management_api.py > "$LOG_DIR/management_api.log" 2>&1 &
    echo $! > "$PID_FILE_MGMT"
    echo -e "${GREEN}✓ Management API started (PID: $(cat $PID_FILE_MGMT))${NC}"
fi

# 等待一下
sleep 2

if [ -f "$PID_FILE_WS" ] && kill -0 $(cat "$PID_FILE_WS") 2>/dev/null; then
    echo -e "${YELLOW}WebSocket Server is already running (PID: $(cat $PID_FILE_WS))${NC}"
else
    # 启动 WebSocket 服务
    echo -e "${GREEN}Starting WebSocket Server on port 9001...${NC}"
    nohup python3 websocket_server.py > "$LOG_DIR/websocket_server.log" 2>&1 &
    echo $! > "$PID_FILE_WS"
    echo -e "${GREEN}✓ WebSocket Server started (PID: $(cat $PID_FILE_WS))${NC}"
fi

echo ""
echo -e "${GREEN}=== GPU Server Started Successfully ===${NC}"
echo ""
echo "Services:"
echo "  - Management API: http://localhost:9000"
echo "  - WebSocket API:  ws://localhost:9001"
echo "  - API Docs:       http://localhost:9000/docs"
echo ""
echo "Logs:"
echo "  - Management API: tail -f $LOG_DIR/management_api.log"
echo "  - WebSocket:      tail -f $LOG_DIR/websocket_server.log"
echo ""
echo "To stop: ./stop.sh"
