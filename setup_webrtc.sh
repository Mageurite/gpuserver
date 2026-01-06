#!/bin/bash

# WebRTC 测试和部署脚本

echo "======================================"
echo "WebRTC 配置和测试脚本"
echo "======================================"
echo ""

# 检查当前目录
if [ ! -d "/workspace/gpuserver" ]; then
    echo "❌ 错误: 请在 /workspace 目录下运行此脚本"
    exit 1
fi

# 显示菜单
show_menu() {
    echo "请选择操作："
    echo "1. 检查 WebRTC 配置"
    echo "2. 启动 GPU Server"
    echo "3. 启动 FRP Client"
    echo "4. 在浏览器中打开测试页面"
    echo "5. 测试 WebSocket 连接"
    echo "6. 检查服务状态"
    echo "7. 查看日志"
    echo "8. 全部启动（Server + FRP）"
    echo "0. 退出"
    echo ""
}

# 检查配置
check_config() {
    echo "📋 检查 WebRTC 配置..."
    echo ""
    
    echo "✅ 1. FRP 配置："
    if [ -f "/workspace/frps/frp_0.66.0_linux_amd64/frpc.toml" ]; then
        echo "   FRP 配置文件存在"
        grep -A 3 "gpu_server_api" /workspace/frps/frp_0.66.0_linux_amd64/frpc.toml | head -4
    else
        echo "   ❌ FRP 配置文件不存在"
    fi
    echo ""
    
    echo "✅ 2. WebRTC Streamer:"
    if [ -f "/workspace/gpuserver/webrtc_streamer.py" ]; then
        echo "   WebRTC Streamer 模块存在"
        echo "   - AvatarVideoTrack: 视频轨道"
        echo "   - WebRTCStreamer: 连接管理器"
    else
        echo "   ❌ WebRTC Streamer 模块不存在"
    fi
    echo ""
    
    echo "✅ 3. WebSocket 信令支持:"
    if grep -q "webrtc_offer" /workspace/gpuserver/api/websocket_server.py; then
        echo "   WebSocket 支持 WebRTC 信令"
        echo "   - webrtc_offer: 处理客户端 offer"
        echo "   - webrtc_answer: 发送服务器 answer"
        echo "   - webrtc_ice_candidate: 处理 ICE candidates"
    else
        echo "   ⚠️  WebSocket 可能不支持 WebRTC 信令"
    fi
    echo ""
    
    echo "✅ 4. 测试页面:"
    if [ -f "/workspace/test_webrtc.html" ]; then
        echo "   测试页面存在: /workspace/test_webrtc.html"
    else
        echo "   ❌ 测试页面不存在"
    fi
    echo ""
    
    echo "✅ 5. 待机视频帧:"
    if [ -d "/workspace/MuseTalk/results/v15/avatars" ]; then
        echo "   Avatar 目录存在"
        avatar_count=$(ls -d /workspace/MuseTalk/results/v15/avatars/avatar_* 2>/dev/null | wc -l)
        echo "   找到 ${avatar_count} 个 Avatar"
    else
        echo "   ⚠️  Avatar 目录不存在（待机视频可能不可用）"
    fi
    echo ""
}

# 启动 GPU Server
start_server() {
    echo "🚀 启动 GPU Server..."
    
    if pgrep -f "unified_server.py" > /dev/null; then
        echo "⚠️  GPU Server 已在运行"
        return
    fi
    
    cd /workspace/gpuserver
    
    if [ -f "./start_server.sh" ]; then
        ./start_server.sh
    else
        echo "手动启动服务器..."
        nohup python unified_server.py > logs/unified_server.log 2>&1 &
        echo "✅ GPU Server 已启动（PID: $!）"
    fi
    
    sleep 2
    check_server_status
}

# 启动 FRP Client
start_frpc() {
    echo "🔗 启动 FRP Client..."
    
    if pgrep -f "frpc" > /dev/null; then
        echo "⚠️  FRP Client 已在运行"
        return
    fi
    
    cd /workspace/frps/frp_0.66.0_linux_amd64
    
    if [ ! -f "./frpc" ]; then
        echo "❌ 错误: frpc 可执行文件不存在"
        return
    fi
    
    if [ ! -f "./frpc.toml" ]; then
        echo "❌ 错误: frpc.toml 配置文件不存在"
        return
    fi
    
    nohup ./frpc -c frpc.toml > /tmp/frpc.log 2>&1 &
    echo "✅ FRP Client 已启动（PID: $!）"
    
    sleep 2
    
    if pgrep -f "frpc" > /dev/null; then
        echo "✅ FRP Client 运行正常"
        echo "   本地端口: 9000"
        echo "   远程端口: 10110"
        echo "   服务器: 51.161.209.200:7504"
    else
        echo "❌ FRP Client 启动失败，查看日志: tail -f /tmp/frpc.log"
    fi
}

# 打开测试页面
open_test_page() {
    echo "🌐 准备打开测试页面..."
    
    if [ ! -f "/workspace/test_webrtc.html" ]; then
        echo "❌ 测试页面不存在"
        return
    fi
    
    echo ""
    echo "测试页面位置: /workspace/test_webrtc.html"
    echo ""
    echo "请在浏览器中打开此文件，或使用以下方式："
    echo ""
    echo "方式 1: 直接打开文件"
    echo "  file:///workspace/test_webrtc.html"
    echo ""
    echo "方式 2: 通过 HTTP 服务器（推荐）"
    echo "  cd /workspace"
    echo "  python3 -m http.server 8080"
    echo "  然后访问: http://localhost:8080/test_webrtc.html"
    echo ""
    echo "方式 3: 复制到前端项目"
    echo "  将 test_webrtc.html 复制到你的前端项目中使用"
    echo ""
}

# 测试 WebSocket 连接
test_websocket() {
    echo "🧪 测试 WebSocket 连接..."
    
    if [ ! -f "/tmp/test_ws.py" ]; then
        echo "创建测试脚本..."
        cat > /tmp/test_ws.py << 'EOF'
import asyncio
import websockets
import json

async def test():
    uri = "ws://localhost:9000/ws/test-session"
    try:
        async with websockets.connect(uri) as ws:
            print("✅ WebSocket 连接成功")
            
            # 发送 WebRTC offer 测试
            await ws.send(json.dumps({
                "type": "webrtc_offer",
                "session_id": "test-123",
                "user_id": 5,
                "avatar_id": "avatar_tutor_13",
                "sdp": "v=0\r\ntest"
            }))
            print("📤 已发送 WebRTC offer")
            
            # 接收响应
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(response)
            print(f"📨 收到响应: {data.get('type')}")
            
            if data.get('type') == 'webrtc_answer':
                print("✅ WebRTC 信令正常工作")
                return True
            else:
                print(f"⚠️  收到非预期响应: {data}")
                return False
                
    except asyncio.TimeoutError:
        print("❌ 连接超时")
        return False
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test())
    exit(0 if result else 1)
EOF
    fi
    
    python3 /tmp/test_ws.py
}

# 检查服务状态
check_server_status() {
    echo "📊 检查服务状态..."
    echo ""
    
    echo "1. GPU Server:"
    if pgrep -f "unified_server.py" > /dev/null; then
        pid=$(pgrep -f "unified_server.py")
        echo "   ✅ 运行中 (PID: $pid)"
        echo "   端口: 9000"
        
        # 检查端口
        if netstat -tuln 2>/dev/null | grep -q ":9000 "; then
            echo "   ✅ 端口 9000 正在监听"
        else
            echo "   ⚠️  端口 9000 未监听"
        fi
    else
        echo "   ❌ 未运行"
    fi
    echo ""
    
    echo "2. FRP Client:"
    if pgrep -f "frpc" > /dev/null; then
        pid=$(pgrep -f "frpc")
        echo "   ✅ 运行中 (PID: $pid)"
        echo "   配置: 9000 -> 51.161.209.200:10110"
    else
        echo "   ❌ 未运行"
    fi
    echo ""
    
    echo "3. WebSocket 端点:"
    echo "   本地: ws://localhost:9000/ws/{session_id}"
    echo "   公网: ws://51.161.209.200:10110/ws/{session_id}"
    echo ""
}

# 查看日志
view_logs() {
    echo "📄 查看日志..."
    echo ""
    echo "选择日志类型："
    echo "1. GPU Server 日志"
    echo "2. FRP Client 日志"
    echo "3. 实时跟踪 GPU Server 日志"
    echo "4. 实时跟踪 FRP Client 日志"
    echo ""
    read -p "请选择 (1-4): " log_choice
    
    case $log_choice in
        1)
            if [ -f "/workspace/gpuserver/logs/unified_server.log" ]; then
                tail -100 /workspace/gpuserver/logs/unified_server.log
            else
                echo "❌ 日志文件不存在"
            fi
            ;;
        2)
            if [ -f "/tmp/frpc.log" ]; then
                tail -100 /tmp/frpc.log
            else
                echo "❌ 日志文件不存在"
            fi
            ;;
        3)
            echo "实时跟踪 GPU Server 日志 (Ctrl+C 退出)..."
            tail -f /workspace/gpuserver/logs/unified_server.log
            ;;
        4)
            echo "实时跟踪 FRP Client 日志 (Ctrl+C 退出)..."
            tail -f /tmp/frpc.log
            ;;
        *)
            echo "无效选择"
            ;;
    esac
}

# 全部启动
start_all() {
    echo "🚀 启动所有服务..."
    echo ""
    
    start_server
    echo ""
    sleep 2
    
    start_frpc
    echo ""
    sleep 2
    
    check_server_status
    
    echo ""
    echo "======================================"
    echo "✅ 所有服务已启动"
    echo "======================================"
    echo ""
    echo "下一步："
    echo "1. 在浏览器中打开测试页面"
    echo "2. 点击 '连接 WebRTC' 按钮"
    echo "3. 等待连接成功后点击 '发送消息'"
    echo "4. 观察视频是否实时播放"
    echo ""
}

# 主循环
while true; do
    show_menu
    read -p "请输入选项 (0-8): " choice
    echo ""
    
    case $choice in
        1) check_config ;;
        2) start_server ;;
        3) start_frpc ;;
        4) open_test_page ;;
        5) test_websocket ;;
        6) check_server_status ;;
        7) view_logs ;;
        8) start_all ;;
        0) 
            echo "👋 再见！"
            exit 0
            ;;
        *)
            echo "❌ 无效选项，请重新选择"
            ;;
    esac
    
    echo ""
    echo "按回车继续..."
    read
    echo ""
done
