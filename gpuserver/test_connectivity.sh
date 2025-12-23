#!/bin/bash
#
# GPU Server 连通性测试脚本
# 测试本地服务和 FRP 远程访问
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
LOCAL_API="http://localhost:9000"
LOCAL_WS="http://localhost:9001"
REMOTE_API="http://51.161.130.234:19000"
REMOTE_WS="http://51.161.130.234:19001"
FRP_SERVER="51.161.130.234:7000"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  GPU Server 连通性测试${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ============================================
# 1. 检查本地服务
# ============================================
echo -e "${YELLOW}[1] 检查本地服务状态${NC}"
echo "----------------------------------------"

# 检查管理 API
if curl -s --connect-timeout 2 "$LOCAL_API/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 管理 API (本地 9000) 运行正常${NC}"
    RESPONSE=$(curl -s "$LOCAL_API/health")
    echo "  响应: $RESPONSE"
else
    echo -e "${RED}✗ 管理 API (本地 9000) 未运行${NC}"
fi

# 检查 WebSocket 服务
if curl -s --connect-timeout 2 "$LOCAL_WS/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ WebSocket 服务 (本地 9001) 运行正常${NC}"
    RESPONSE=$(curl -s "$LOCAL_WS/health")
    echo "  响应: $RESPONSE"
else
    echo -e "${RED}✗ WebSocket 服务 (本地 9001) 未运行${NC}"
fi

echo ""

# ============================================
# 2. 检查 FRP 客户端
# ============================================
echo -e "${YELLOW}[2] 检查 FRP 客户端状态${NC}"
echo "----------------------------------------"

if pgrep -f "frpc.*frpc.ini" > /dev/null; then
    FRPC_PID=$(pgrep -f "frpc.*frpc.ini" | head -1)
    echo -e "${GREEN}✓ frpc 正在运行 (PID: $FRPC_PID)${NC}"
    
    # 检查 frpc 连接状态
    if netstat -an 2>/dev/null | grep -q "$FRP_SERVER.*ESTABLISHED" || \
       ss -an 2>/dev/null | grep -q "$FRP_SERVER.*ESTABLISHED"; then
        echo -e "${GREEN}✓ frpc 已连接到 frps ($FRP_SERVER)${NC}"
    else
        echo -e "${YELLOW}⚠ frpc 运行中，但连接状态未知${NC}"
    fi
else
    echo -e "${RED}✗ frpc 未运行${NC}"
    echo "  提示: 运行 ./start_frpc.sh 启动 frpc"
fi

echo ""

# ============================================
# 3. 测试 FRP 远程访问
# ============================================
echo -e "${YELLOW}[3] 测试 FRP 远程访问${NC}"
echo "----------------------------------------"

# 测试远程管理 API
echo -n "测试远程管理 API ($REMOTE_API)... "
if curl -s --connect-timeout 5 "$REMOTE_API/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 成功${NC}"
    RESPONSE=$(curl -s "$REMOTE_API/health")
    echo "  响应: $RESPONSE"
else
    echo -e "${RED}✗ 失败${NC}"
    echo "  可能原因:"
    echo "    - frps 服务未运行"
    echo "    - 防火墙阻止了端口 19000"
    echo "    - frpc 连接未建立"
fi

# 测试远程 WebSocket 服务
echo -n "测试远程 WebSocket 服务 ($REMOTE_WS)... "
if curl -s --connect-timeout 5 "$REMOTE_WS/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 成功${NC}"
    RESPONSE=$(curl -s "$REMOTE_WS/health")
    echo "  响应: $RESPONSE"
else
    echo -e "${RED}✗ 失败${NC}"
    echo "  可能原因:"
    echo "    - frps 服务未运行"
    echo "    - 防火墙阻止了端口 19001"
    echo "    - frpc 连接未建立"
fi

echo ""

# ============================================
# 4. 测试会话创建（通过 FRP）
# ============================================
echo -e "${YELLOW}[4] 测试会话创建（通过 FRP）${NC}"
echo "----------------------------------------"

SESSION_RESPONSE=$(curl -s --connect-timeout 5 -X POST "$REMOTE_API/v1/sessions" \
    -H "Content-Type: application/json" \
    -d '{"tutor_id": 1, "student_id": 1, "kb_id": "test-kb"}')

if echo "$SESSION_RESPONSE" | grep -q "session_id"; then
    echo -e "${GREEN}✓ 会话创建成功${NC}"
    SESSION_ID=$(echo "$SESSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['session_id'])" 2>/dev/null || echo "N/A")
    ENGINE_TOKEN=$(echo "$SESSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['engine_token'])" 2>/dev/null || echo "N/A")
    echo "  会话 ID: $SESSION_ID"
    echo "  Token: ${ENGINE_TOKEN:0:20}..."
    echo "  完整响应:"
    echo "$SESSION_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$SESSION_RESPONSE"
else
    echo -e "${RED}✗ 会话创建失败${NC}"
    echo "  响应: $SESSION_RESPONSE"
fi

echo ""

# ============================================
# 5. 端口监听状态
# ============================================
echo -e "${YELLOW}[5] 端口监听状态${NC}"
echo "----------------------------------------"

check_port() {
    local port=$1
    local name=$2
    if netstat -tlnp 2>/dev/null | grep -q ":$port " || \
       ss -tlnp 2>/dev/null | grep -q ":$port "; then
        echo -e "${GREEN}✓ $name (端口 $port) 正在监听${NC}"
    else
        echo -e "${RED}✗ $name (端口 $port) 未监听${NC}"
    fi
}

check_port 9000 "管理 API"
check_port 9001 "WebSocket 服务"

echo ""

# ============================================
# 总结
# ============================================
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  测试完成${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "访问地址："
echo "  本地管理 API:  $LOCAL_API"
echo "  本地 WebSocket: $LOCAL_WS"
echo "  远程管理 API:  $REMOTE_API"
echo "  远程 WebSocket: $REMOTE_WS"
echo ""
echo "API 文档："
echo "  $LOCAL_API/docs"
echo "  $REMOTE_API/docs"
echo ""

