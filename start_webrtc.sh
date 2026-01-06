#!/bin/bash
# WebRTC 快速启动脚本

echo "=========================================="
echo "🚀 WebRTC 快速启动"
echo "=========================================="
echo ""

# 1. 启动 GPU Server
echo "1️⃣ 启动 GPU Server..."
cd /workspace/gpuserver

if pgrep -f "unified_server.py" > /dev/null; then
    echo "   ⚠️  GPU Server 已在运行"
else
    if [ -f "./start_server.sh" ]; then
        ./start_server.sh &
        sleep 3
        echo "   ✅ GPU Server 已启动"
    else
        echo "   ❌ start_server.sh 不存在"
        exit 1
    fi
fi

# 2. 启动 FRP Client
echo ""
echo "2️⃣ 启动 FRP Client..."
cd /workspace/frps/frp_0.66.0_linux_amd64

if pgrep -f "frpc" > /dev/null; then
    echo "   ⚠️  FRP Client 已在运行"
else
    nohup ./frpc -c frpc.toml > /tmp/frpc.log 2>&1 &
    sleep 2
    
    if pgrep -f "frpc" > /dev/null; then
        echo "   ✅ FRP Client 已启动"
    else
        echo "   ❌ FRP Client 启动失败"
        exit 1
    fi
fi

# 3. 验证配置
echo ""
echo "3️⃣ 验证配置..."
sleep 1

# 检查端口
if netstat -tuln 2>/dev/null | grep -q ":9000 "; then
    echo "   ✅ GPU Server 端口 9000 正在监听"
else
    echo "   ⚠️  GPU Server 端口 9000 未监听"
fi

# 4. 显示配置信息
echo ""
echo "=========================================="
echo "✅ 服务已启动"
echo "=========================================="
echo ""
echo "📋 核心配置："
echo ""
echo "1. ICE 服务器"
echo "   - STUN: stun:stun.l.google.com:19302"
echo "   - TURN: turn:51.161.209.200:10110?transport=udp"
echo "   - 认证: vtuser / vtpass"
echo ""
echo "2. 端口映射"
echo "   - WebSocket: ws://51.161.209.200:10110/ws/{session_id}"
echo "   - TURN: UDP 10110"
echo "   - 媒体: UDP 10111-10115"
echo ""
echo "3. 公网 IP 替换"
echo "   - 私网IP → 51.161.209.200"
echo ""
echo "=========================================="
echo "🧪 测试方法"
echo "=========================================="
echo ""
echo "方法 1: 浏览器测试（推荐）"
echo "  打开文件: /workspace/test_webrtc.html"
echo ""
echo "方法 2: 启动 HTTP 服务器"
echo "  cd /workspace"
echo "  python3 -m http.server 8080"
echo "  访问: http://localhost:8080/test_webrtc.html"
echo ""
echo "方法 3: 验证配置"
echo "  /workspace/verify_webrtc_config.sh"
echo ""
echo "=========================================="
echo "📊 查看日志"
echo "=========================================="
echo ""
echo "GPU Server: tail -f /workspace/gpuserver/logs/unified_server.log"
echo "FRP Client: tail -f /tmp/frpc.log"
echo ""
echo "🎉 准备就绪，可以开始测试！"
echo ""
