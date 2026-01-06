#!/bin/bash

# WebRTC 配置验证脚本

echo "======================================"
echo "WebRTC 配置验证"
echo "======================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_pass() {
    echo -e "${GREEN}✅ $1${NC}"
}

check_fail() {
    echo -e "${RED}❌ $1${NC}"
}

check_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

echo "1️⃣ 检查 ICE 服务器配置..."
echo ""

# 检查 config.py
if grep -q "turn_server" /workspace/gpuserver/config.py; then
    check_pass "config.py 包含 TURN 服务器配置"
    echo "   TURN Server: $(grep 'turn_server:' /workspace/gpuserver/config.py | cut -d'"' -f2)"
    echo "   Username: $(grep 'turn_username:' /workspace/gpuserver/config.py | cut -d'"' -f2)"
else
    check_fail "config.py 缺少 TURN 配置"
fi

echo ""

# 检查 webrtc_streamer.py
if grep -q "stun:stun.l.google.com" /workspace/gpuserver/webrtc_streamer.py; then
    check_pass "webrtc_streamer.py 配置了 STUN 服务器"
else
    check_fail "webrtc_streamer.py 缺少 STUN 配置"
fi

if grep -q "turn_server" /workspace/gpuserver/webrtc_streamer.py; then
    check_pass "webrtc_streamer.py 配置了 TURN 服务器"
else
    check_fail "webrtc_streamer.py 缺少 TURN 配置"
fi

echo ""
echo "2️⃣ 检查 IP 替换逻辑..."
echo ""

if grep -q "_replace_private_ip_in_sdp" /workspace/gpuserver/webrtc_streamer.py; then
    check_pass "实现了 _replace_private_ip_in_sdp 函数"
    
    # 检查是否在 handle_offer 中调用
    if grep -A 20 "async def handle_offer" /workspace/gpuserver/webrtc_streamer.py | grep -q "_replace_private_ip_in_sdp"; then
        check_pass "handle_offer 中调用了 IP 替换"
    else
        check_fail "handle_offer 中未调用 IP 替换"
    fi
else
    check_fail "缺少 _replace_private_ip_in_sdp 函数"
fi

echo ""
echo "3️⃣ 检查 FRP 端口映射..."
echo ""

FRP_CONFIG="/workspace/frps/frp_0.66.0_linux_amd64/frpc.toml"

if [ -f "$FRP_CONFIG" ]; then
    check_pass "FRP 配置文件存在"
    
    # 检查 TCP 10110 (WebSocket)
    if grep -A 5 "gpu_server_api" "$FRP_CONFIG" | grep -q "remotePort = 10110"; then
        check_pass "TCP 10110 已映射 (WebSocket 信令)"
    else
        check_fail "TCP 10110 未映射"
    fi
    
    # 检查 UDP 10110 (TURN)
    if grep -q "turn_server" "$FRP_CONFIG"; then
        check_pass "UDP 10110 已映射 (TURN 服务器)"
    else
        check_warn "UDP 10110 未映射 (TURN 可能无法工作)"
    fi
    
    # 检查 UDP 10111-10115 (媒体端口)
    udp_count=$(grep -c "type = \"udp\"" "$FRP_CONFIG")
    if [ "$udp_count" -ge 5 ]; then
        check_pass "UDP 媒体端口已映射 ($udp_count 个)"
    else
        check_warn "UDP 端口数量可能不足 (当前: $udp_count)"
    fi
else
    check_fail "FRP 配置文件不存在"
fi

echo ""
echo "4️⃣ 检查前端配置..."
echo ""

if [ -f "/workspace/test_webrtc.html" ]; then
    check_pass "测试页面存在"
    
    # 检查 STUN 配置
    if grep -q "stun:stun.l.google.com" /workspace/test_webrtc.html; then
        check_pass "前端配置了 STUN"
    else
        check_fail "前端缺少 STUN 配置"
    fi
    
    # 检查 TURN 配置
    if grep -q "turn:51.161.209.200:10110" /workspace/test_webrtc.html; then
        check_pass "前端配置了 TURN"
    else
        check_fail "前端缺少 TURN 配置"
    fi
else
    check_warn "测试页面不存在"
fi

echo ""
echo "5️⃣ 检查公网 IP 配置..."
echo ""

PUBLIC_IP="51.161.209.200"

if grep -q "webrtc_public_ip.*$PUBLIC_IP" /workspace/gpuserver/config.py; then
    check_pass "公网 IP 已配置: $PUBLIC_IP"
else
    check_fail "公网 IP 配置错误或缺失"
fi

echo ""
echo "======================================"
echo "总结"
echo "======================================"
echo ""

# 计算通过的检查项
pass_count=$(grep -c "✅" <<< "$(bash $0 2>&1)" || echo "0")

echo "核心配置要点："
echo ""
echo "1. ICE 服务器配置"
echo "   - STUN: stun:stun.l.google.com:19302"
echo "   - TURN: turn:51.161.209.200:10110?transport=udp"
echo "   - 认证: vtuser / vtpass"
echo ""
echo "2. 公网 IP 替换"
echo "   - 函数: _replace_private_ip_in_sdp()"
echo "   - 目标: 192.168.x.x → 51.161.209.200"
echo ""
echo "3. FRP 端口映射"
echo "   - TCP 10110: WebSocket 信令"
echo "   - UDP 10110: TURN 服务器"
echo "   - UDP 10111-10115: WebRTC 媒体"
echo ""

if [ -f "$FRP_CONFIG" ]; then
    echo "当前 FRP 配置："
    echo "----------------------------------------"
    grep -A 3 "gpu_server_api\|turn_server\|udp_1011" "$FRP_CONFIG" | head -20
    echo "----------------------------------------"
fi

echo ""
echo "下一步："
echo "1. 启动 GPU Server: cd /workspace/gpuserver && ./start_server.sh"
echo "2. 启动 FRP Client: cd /workspace/frps/frp_0.66.0_linux_amd64 && ./frpc -c frpc.toml"
echo "3. 测试连接: 打开 /workspace/test_webrtc.html"
echo ""
