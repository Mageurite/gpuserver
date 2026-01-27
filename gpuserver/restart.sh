#!/bin/bash
# 完整重启脚本：清理端口 + 重启 TURN + 重启 WebSocket Server

echo "=== 停止服务 ==="
pkill -9 -f "python.*websocket_server" 2>/dev/null
pkill -9 turnserver 2>/dev/null
sleep 2

echo "=== 等待端口释放 ==="
while ss -tulnp | grep -q ":9001 "; do
    echo "等待端口 9001..."
    sleep 1
done

echo "=== 启动 TURN 服务器 ==="
turnserver -c /etc/turnserver.conf -o &
sleep 2

echo "=== 启动 WebSocket 服务器 ==="
cd /workspace/gpuserver
rm -f logs/websocket_server_console.log
PYTHONPATH=/workspace/gpuserver:$PYTHONPATH setsid /workspace/conda_envs/rag/bin/python api/websocket_server.py > logs/websocket_server_console.log 2>&1 &
disown

echo "=== 等待启动 (15秒) ==="
sleep 15

echo "=== 状态检查 ==="
if ps aux | grep -v grep | grep -q "websocket_server"; then
    echo "✅ WebSocket Server 已启动"
    ps aux | grep websocket_server | grep python | grep -v grep | awk '{print "   PID:", $2}'
else
    echo "❌ WebSocket Server 启动失败"
    tail -20 logs/websocket_server_console.log
fi

if ps aux | grep -v grep | grep -q "turnserver"; then
    echo "✅ TURN Server 已启动"
    ps aux | grep turnserver | grep -v grep | awk '{print "   PID:", $2}'
else
    echo "❌ TURN Server 启动失败"
fi

echo ""
echo "=== 端口状态 ==="
ss -tulnp | grep -E "(9001|10110)" | head -5
