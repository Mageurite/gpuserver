#!/bin/bash

# GPU Server 完整重启脚本
# 包含 TURN 服务器和 GPU 服务器（WebSocket + Management API）

echo "=========================================="
echo "GPU Server Complete Restart Script"
echo "=========================================="

# 1. 重启 TURN 服务器
echo ""
echo "Step 1: 重启 TURN 服务器..."
/workspace/gpuserver/scripts/restart_turn.sh

# 2. 重启 GPU 服务器
echo ""
echo "Step 2: 重启 GPU 服务器..."

# 停止现有服务
echo "   停止现有服务..."
ps aux | grep -E "(management_api|websocket_server)" | grep python | grep -v grep | awk '{print $2}' | xargs -r kill
sleep 2
echo "   ✅ GPU 服务已停止"

# 启动 WebSocket 服务器
echo "   启动 WebSocket 服务器..."
cd /workspace/gpuserver
PYTHONPATH=/workspace/gpuserver:$PYTHONPATH nohup /workspace/conda_envs/rag/bin/python api/websocket_server.py > logs/websocket_server_console.log 2>&1 &
sleep 2

# 启动 Management API
echo "   启动 Management API..."
PYTHONPATH=/workspace/gpuserver:$PYTHONPATH nohup /workspace/conda_envs/rag/bin/python api/management_api.py > logs/management_api_console.log 2>&1 &
sleep 3

# 3. 验证服务状态
echo ""
echo "Step 3: 验证服务状态..."

# 检查进程
PROCESS_COUNT=$(ps aux | grep -E "(management_api|websocket_server)" | grep python | grep -v grep | wc -l)
echo "   GPU 服务进程数: $PROCESS_COUNT"

# 健康检查
echo "   执行健康检查..."
HEALTH_RESPONSE=$(curl -s http://localhost:9000/health 2>/dev/null)
if [ -n "$HEALTH_RESPONSE" ]; then
    echo "   ✅ 健康检查通过"
    echo "   响应: $HEALTH_RESPONSE"
else
    echo "   ❌ 健康检查失败"
    exit 1
fi

# 4. 显示服务信息
echo ""
echo "=========================================="
echo "✅ 所有服务重启完成！"
echo "=========================================="
echo ""
echo "服务状态："
echo "  - TURN 服务器: 运行中 (PID: $(pgrep turnserver))"
echo "  - WebSocket 服务器: 运行中 (端口 9001)"
echo "  - Management API: 运行中 (端口 9000)"
echo ""
echo "端口状态："
ss -tulnp | grep -E "101(10|11|12|13|14|15)" | wc -l | awk '{print "  - TURN 端口占用: " $1 " 个"}'
echo ""
echo "可用命令："
echo "  - 仅重启 TURN: /workspace/gpuserver/scripts/restart_turn.sh"
echo "  - 完整重启: /workspace/gpuserver/scripts/restart_all.sh"
echo "  - 查看日志: tail -f /workspace/gpuserver/logs/websocket_server_console.log"
echo "=========================================="
