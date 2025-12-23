#!/bin/bash
#
# GPU Server 停止脚本
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志目录
LOG_DIR="logs"

# PID 文件
PID_FILE_MGMT="$LOG_DIR/management_api.pid"
PID_FILE_WS="$LOG_DIR/websocket_server.pid"

echo -e "${YELLOW}=== Stopping GPU Server ===${NC}"

# 停止管理 API
if [ -f "$PID_FILE_MGMT" ]; then
    PID=$(cat "$PID_FILE_MGMT")
    if kill -0 "$PID" 2>/dev/null; then
        echo -e "${YELLOW}Stopping Management API (PID: $PID)...${NC}"
        kill "$PID"
        rm "$PID_FILE_MGMT"
        echo -e "${GREEN}✓ Management API stopped${NC}"
    else
        echo -e "${RED}Management API not running${NC}"
        rm "$PID_FILE_MGMT"
    fi
else
    echo -e "${RED}Management API PID file not found${NC}"
fi

# 停止 WebSocket 服务
if [ -f "$PID_FILE_WS" ]; then
    PID=$(cat "$PID_FILE_WS")
    if kill -0 "$PID" 2>/dev/null; then
        echo -e "${YELLOW}Stopping WebSocket Server (PID: $PID)...${NC}"
        kill "$PID"
        rm "$PID_FILE_WS"
        echo -e "${GREEN}✓ WebSocket Server stopped${NC}"
    else
        echo -e "${RED}WebSocket Server not running${NC}"
        rm "$PID_FILE_WS"
    fi
else
    echo -e "${RED}WebSocket Server PID file not found${NC}"
fi

echo ""
echo -e "${GREEN}=== GPU Server Stopped ===${NC}"
