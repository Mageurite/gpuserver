#!/bin/bash

# TURN 服务器重启脚本
# 用于清理端口占用和重启服务

echo "=========================================="
echo "TURN Server Restart Script"
echo "=========================================="

# 1. 检查当前端口占用
echo ""
echo "1. 检查当前端口占用..."
TURN_SOCKETS=$(ss -tulnp | grep turnserver | wc -l)
echo "   当前 TURN socket 数量: $TURN_SOCKETS"

PORT_COUNT=$(ss -tulnp | grep -E "101(10|11|12|13|14|15)" | wc -l)
echo "   端口 10110-10115 占用: $PORT_COUNT"

# 2. 停止 TURN 服务器
echo ""
echo "2. 停止 TURN 服务器..."
TURN_PID=$(ps aux | grep turnserver | grep -v grep | awk '{print $2}')
if [ -n "$TURN_PID" ]; then
    echo "   正在停止 TURN (PID: $TURN_PID)..."
    kill -9 $TURN_PID 2>/dev/null
    sleep 2
    echo "   ✅ TURN 已停止"
else
    echo "   ⚠️ TURN 未运行"
fi

# 3. 验证端口已清理
echo ""
echo "3. 验证端口清理..."
sleep 1
PORT_COUNT_AFTER=$(ss -tulnp | grep -E "101(10|11|12|13|14|15)" | wc -l)
echo "   清理后端口占用: $PORT_COUNT_AFTER"

# 4. 重启 TURN 服务器
echo ""
echo "4. 重启 TURN 服务器..."
turnserver -c /etc/turnserver.conf -o > /dev/null 2>&1 &
sleep 3

# 5. 验证启动成功
NEW_PID=$(ps aux | grep turnserver | grep -v grep | awk '{print $2}')
if [ -n "$NEW_PID" ]; then
    echo "   ✅ TURN 已启动 (PID: $NEW_PID)"
    
    # 测试连接
    echo ""
    echo "5. 测试 TURN 连接..."
    python3 << 'EOPYTHON'
import socket
import struct

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    msg_type = 0x0001
    packet = struct.pack('!HHI12s', msg_type, 0, 0x2112A442, b'\x00' * 12)
    sock.sendto(packet, ('127.0.0.1', 10110))
    data, addr = sock.recvfrom(1024)
    print("   ✅ TURN 连接测试成功")
    sock.close()
except Exception as e:
    print(f"   ❌ TURN 连接测试失败: {e}")
EOPYTHON
else
    echo "   ❌ TURN 启动失败"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ TURN 服务器重启完成！"
echo "=========================================="
