#!/bin/bash
#
# TURN Server Port Cleanup Script
# 定期重启TURN服务器以释放占用的端口
#
# 使用方法:
#   1. 手动运行: bash /workspace/gpuserver/scripts/cleanup_turn.sh
#   2. 定时任务: 添加到crontab (每30分钟运行一次)
#      */30 * * * * /workspace/gpuserver/scripts/cleanup_turn.sh >> /var/log/turn_cleanup.log 2>&1
#

TURN_CONFIG="/etc/turnserver.conf"
LOG_FILE="/var/log/turn_cleanup.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting TURN server cleanup..."

# 查找turnserver进程
TURN_PID=$(ps aux | grep turnserver | grep -v grep | awk '{print $2}')

if [ -z "$TURN_PID" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] TURN server is not running. Starting it..."
    turnserver -c $TURN_CONFIG -o &
    sleep 2
    NEW_PID=$(ps aux | grep turnserver | grep -v grep | awk '{print $2}')
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] TURN server started with PID: $NEW_PID"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Found TURN server with PID: $TURN_PID"

    # 检查端口使用情况
    PORT_COUNT=$(ss -tulnp | grep -c "10110\|10111\|10112\|10113\|10114\|10115")
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Current port usage: $PORT_COUNT sockets"

    # 如果端口使用过多(超过100个socket),重启TURN服务器
    if [ $PORT_COUNT -gt 100 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Port usage is high ($PORT_COUNT). Restarting TURN server..."
        kill -9 $TURN_PID
        sleep 2
        turnserver -c $TURN_CONFIG -o &
        sleep 2
        NEW_PID=$(ps aux | grep turnserver | grep -v grep | awk '{print $2}')
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] TURN server restarted with PID: $NEW_PID"

        # 验证重启后的端口使用
        NEW_PORT_COUNT=$(ss -tulnp | grep -c "10110\|10111\|10112\|10113\|10114\|10115")
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Port usage after restart: $NEW_PORT_COUNT sockets"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Port usage is acceptable. No restart needed."
    fi
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleanup completed."
echo "----------------------------------------"
