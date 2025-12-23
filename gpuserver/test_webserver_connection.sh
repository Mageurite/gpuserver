#!/bin/bash
# GPU Server 与 Web Server 连接测试脚本
# 测试 GPU Server 和 Web Server 之间的连通性

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "  GPU Server ↔ Web Server 连接测试"
echo "=========================================="
echo ""

# 加载环境变量
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

GPU_PORT=${MANAGEMENT_API_PORT:-9000}
WEB_PORT=${WEB_SERVER_PORT:-8000}

# 测试 1: GPU Server 健康检查
echo -e "${BLUE}[1] GPU Server 健康检查${NC}"
if curl -s http://localhost:$GPU_PORT/health > /dev/null 2>&1; then
    HEALTH_RESPONSE=$(curl -s http://localhost:$GPU_PORT/health)
    echo -e "${GREEN}✓ GPU Server 运行正常${NC}"
    echo "  地址: http://localhost:$GPU_PORT"
    echo "  响应: $HEALTH_RESPONSE"
else
    echo -e "${RED}✗ GPU Server 无法访问${NC}"
    echo "  请先启动 GPU Server: ./start.sh"
    exit 1
fi

echo ""

# 测试 2: Web Server 健康检查
echo -e "${BLUE}[2] Web Server 健康检查${NC}"
if curl -s http://localhost:$WEB_PORT/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Web Server 运行正常${NC}"
    echo "  地址: http://localhost:$WEB_PORT"
else
    echo -e "${YELLOW}! Web Server 无法访问${NC}"
    echo "  Web Server 可能未启动或使用不同端口"
    echo "  提示: 检查 /workspace/virtual_tutor/app_backend"
fi

echo ""

# 测试 3: 检查 Web Server 的 ENGINE_URL 配置
echo -e "${BLUE}[3] Web Server ENGINE_URL 配置${NC}"
WEB_ENV="/workspace/virtual_tutor/app_backend/.env"

if [ -f "$WEB_ENV" ]; then
    if grep -q "ENGINE_URL" "$WEB_ENV"; then
        ENGINE_URL=$(grep "ENGINE_URL" "$WEB_ENV" | cut -d'=' -f2 | tr -d ' "'"'"'')
        echo -e "${GREEN}✓ ENGINE_URL 已配置${NC}"
        echo "  配置值: $ENGINE_URL"

        # 检查配置是否指向当前 GPU Server
        if echo "$ENGINE_URL" | grep -q ":$GPU_PORT"; then
            echo -e "  ${GREEN}✓ 端口匹配${NC}"
        else
            echo -e "  ${YELLOW}! 端口可能不匹配（GPU Server: $GPU_PORT）${NC}"
        fi
    else
        echo -e "${YELLOW}! ENGINE_URL 未配置${NC}"
        echo "  Web Server 可能使用 Mock 模式"
        echo "  建议在 $WEB_ENV 中添加："
        echo "  ENGINE_URL=http://localhost:$GPU_PORT"
    fi
else
    echo -e "${YELLOW}! Web Server .env 文件不存在${NC}"
    echo "  路径: $WEB_ENV"
fi

echo ""

# 测试 4: 测试创建会话（模拟 Web Server 调用）
echo -e "${BLUE}[4] 测试会话创建（模拟 Web Server 调用）${NC}"

# 创建测试会话
CREATE_RESPONSE=$(curl -s -X POST http://localhost:$GPU_PORT/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tutor_id": 1, "student_id": 999, "kb_id": "test-kb"}' 2>&1)

if echo "$CREATE_RESPONSE" | grep -q "session_id"; then
    echo -e "${GREEN}✓ 会话创建成功${NC}"

    # 提取会话信息
    SESSION_ID=$(echo "$CREATE_RESPONSE" | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)
    ENGINE_URL=$(echo "$CREATE_RESPONSE" | grep -o '"engine_url":"[^"]*"' | cut -d'"' -f4)
    ENGINE_TOKEN=$(echo "$CREATE_RESPONSE" | grep -o '"engine_token":"[^"]*"' | cut -d'"' -f4)

    echo "  会话 ID: $SESSION_ID"
    echo "  WebSocket URL: $ENGINE_URL"
    echo "  Token: ${ENGINE_TOKEN:0:20}..."

    # 测试查询会话
    echo ""
    echo -e "${BLUE}[5] 测试查询会话${NC}"
    QUERY_RESPONSE=$(curl -s http://localhost:$GPU_PORT/v1/sessions/$SESSION_ID)

    if echo "$QUERY_RESPONSE" | grep -q "session_id"; then
        echo -e "${GREEN}✓ 会话查询成功${NC}"
        STATUS=$(echo "$QUERY_RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        echo "  状态: $STATUS"
    else
        echo -e "${RED}✗ 会话查询失败${NC}"
    fi

    # 测试 WebSocket 连接（如果安装了 websocat 或 wscat）
    echo ""
    echo -e "${BLUE}[6] WebSocket 连接测试${NC}"

    if command -v python3 &> /dev/null; then
        # 使用 Python 测试 WebSocket
        echo "  正在测试 WebSocket 连接..."

        python3 -c "
import asyncio
import websockets
import json
import sys

async def test_websocket():
    uri = '$ENGINE_URL?token=$ENGINE_TOKEN'
    try:
        # 修复：使用 asyncio.wait_for 来设置连接超时，而不是 websockets.connect 的 timeout 参数
        websocket = await asyncio.wait_for(
            websockets.connect(uri),
            timeout=5
        )
        try:
            # 等待欢迎消息
            welcome = await asyncio.wait_for(websocket.recv(), timeout=5)
            print('${GREEN}✓ WebSocket 连接成功${NC}')
            print(f'  收到欢迎消息: {welcome[:100]}...')

            # 发送测试消息
            test_msg = {'type': 'text', 'content': '测试连接'}
            await websocket.send(json.dumps(test_msg))

            # 等待响应
            response = await asyncio.wait_for(websocket.recv(), timeout=10)
            print(f'  收到响应: {response[:100]}...')

            return True
        finally:
            await websocket.close()
    except asyncio.TimeoutError:
        print('${YELLOW}! WebSocket 连接超时${NC}')
        return False
    except Exception as e:
        print(f'${RED}✗ WebSocket 连接失败: {e}${NC}')
        return False

try:
    result = asyncio.run(test_websocket())
    sys.exit(0 if result else 1)
except ImportError:
    print('${YELLOW}! websockets 模块未安装，跳过 WebSocket 测试${NC}')
    print('  安装: pip install websockets')
    sys.exit(2)
" 2>&1

        WS_TEST_RESULT=$?

        if [ $WS_TEST_RESULT -eq 2 ]; then
            echo -e "${YELLOW}  提示: 安装 websockets 模块以进行完整测试${NC}"
            echo "  pip install websockets"
        fi
    else
        echo -e "${YELLOW}! Python3 未安装，跳过 WebSocket 测试${NC}"
    fi

    # 清理测试会话
    echo ""
    echo -e "${BLUE}[7] 清理测试会话${NC}"
    DELETE_RESPONSE=$(curl -s -X DELETE http://localhost:$GPU_PORT/v1/sessions/$SESSION_ID)

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 测试会话已删除${NC}"
    else
        echo -e "${YELLOW}! 删除会话时出现问题${NC}"
    fi

else
    echo -e "${RED}✗ 会话创建失败${NC}"
    echo "  响应: $CREATE_RESPONSE"
fi

echo ""

# 测试 5: 网络连通性测试
echo -e "${BLUE}[8] 网络连通性总结${NC}"

# 检查是否在同一台机器
if [ -f "$WEB_ENV" ]; then
    echo -e "${GREEN}✓ GPU Server 和 Web Server 在同一机器${NC}"
    echo "  建议配置: ENGINE_URL=http://localhost:$GPU_PORT"
else
    echo -e "${YELLOW}! Web Server 可能在不同机器${NC}"
    echo "  如果 Web Server 在不同机器，需要配置公网 IP"
    echo "  建议配置: ENGINE_URL=http://<gpu-server-ip>:$GPU_PORT"

    # 显示当前机器 IP
    if command -v hostname &> /dev/null; then
        HOSTNAME=$(hostname -I | awk '{print $1}')
        echo "  当前机器 IP: $HOSTNAME"
        echo "  可使用: ENGINE_URL=http://$HOSTNAME:$GPU_PORT"
    fi
fi

echo ""

# 总结
echo "=========================================="
echo -e "${BLUE}连接测试总结${NC}"
echo "=========================================="
echo ""
echo "如果所有测试通过，说明 GPU Server 和 Web Server 可以正常通信。"
echo ""
echo "Web Server 配置步骤："
echo "1. 编辑 Web Server 配置文件:"
echo "   vim /workspace/virtual_tutor/app_backend/.env"
echo ""
echo "2. 添加或修改 ENGINE_URL:"
echo "   ENGINE_URL=http://localhost:$GPU_PORT"
echo ""
echo "3. 重启 Web Server:"
echo "   cd /workspace/virtual_tutor/app_backend"
echo "   # 停止旧进程"
echo "   pkill -f 'uvicorn app.main:app'"
echo "   # 启动新进程"
echo "   uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "4. 验证连接:"
echo "   # 查看 Web Server 日志，应该显示连接到 GPU Server"
echo "   # 创建一个测试会话，应该返回 engine_url"
echo ""
echo "=========================================="
echo ""
