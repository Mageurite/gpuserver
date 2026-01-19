#!/bin/bash
#
# Quick TURN Reset Script
# 快速重启TURN服务器,释放所有端口
#

TURN_CONFIG="/etc/turnserver.conf"

echo "Stopping TURN server..."
pkill -9 turnserver 2>/dev/null
sleep 1

echo "Starting TURN server..."
turnserver -c $TURN_CONFIG -o &
sleep 2

NEW_PID=$(ps aux | grep turnserver | grep -v grep | awk '{print $2}')
echo "TURN server running with PID: $NEW_PID"

# 显示端口状态
PORT_COUNT=$(ss -tulnp | grep -c "turnserver" 2>/dev/null || echo "0")
echo "Active sockets: $PORT_COUNT"
