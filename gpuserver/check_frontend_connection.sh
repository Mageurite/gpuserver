#!/bin/bash
# 完整的前端到 GPU Server 连接检查脚本
# 检查整个链路：前端 → Web Server → GPU Server

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "  前端连接状态完整检查"
echo "  前端 → Web Server → GPU Server"
echo "=========================================="
echo ""

# 检查所有服务
FRONTEND_PORT=3000
WEBSERVER_PORT=8000
GPUSERVER_PORT=9000

ALL_OK=true

# 1. 检查 GPU Server
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}[1/3] GPU Server (Port $GPUSERVER_PORT)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if curl -s http://localhost:$GPUSERVER_PORT/health > /dev/null 2>&1; then
    HEALTH=$(curl -s http://localhost:$GPUSERVER_PORT/health)
    echo -e "${GREEN}✓ GPU Server 运行正常${NC}"
    echo "  地址: http://localhost:$GPUSERVER_PORT"
    echo "  响应: $HEALTH"
else
    echo -e "${RED}✗ GPU Server 未运行${NC}"
    echo "  启动命令: cd /workspace/gpuserver && ./start.sh"
    ALL_OK=false
fi

echo ""

# 2. 检查 Web Server
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}[2/3] Web Server (Port $WEBSERVER_PORT)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if curl -s http://localhost:$WEBSERVER_PORT/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Web Server 运行正常${NC}"
    echo "  地址: http://localhost:$WEBSERVER_PORT"

    # 检查 ENGINE_URL 配置
    WEB_ENV="/workspace/virtual_tutor/app_backend/.env"
    if [ -f "$WEB_ENV" ]; then
        if grep -q "ENGINE_URL" "$WEB_ENV"; then
            ENGINE_URL=$(grep "ENGINE_URL" "$WEB_ENV" | cut -d'=' -f2 | tr -d ' "'"'"'')
            echo -e "${GREEN}  ✓ ENGINE_URL 已配置: $ENGINE_URL${NC}"

            # 测试连接到 GPU Server
            if echo "$ENGINE_URL" | grep -q ":$GPUSERVER_PORT"; then
                echo -e "${GREEN}  ✓ ENGINE_URL 端口正确${NC}"
            else
                echo -e "${YELLOW}  ! ENGINE_URL 端口可能不匹配${NC}"
                echo "    应该是: http://localhost:$GPUSERVER_PORT"
            fi
        else
            echo -e "${RED}  ✗ ENGINE_URL 未配置${NC}"
            echo "    请在 $WEB_ENV 中添加："
            echo "    ENGINE_URL=http://localhost:$GPUSERVER_PORT"
            ALL_OK=false
        fi
    else
        echo -e "${YELLOW}  ! .env 文件不存在: $WEB_ENV${NC}"
        ALL_OK=false
    fi
else
    echo -e "${RED}✗ Web Server 未运行${NC}"
    echo "  启动命令:"
    echo "    cd /workspace/virtual_tutor/app_backend"
    echo "    uvicorn app.main:app --host 0.0.0.0 --port $WEBSERVER_PORT"
    ALL_OK=false
fi

echo ""

# 3. 检查前端
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}[3/3] 前端 (Port $FRONTEND_PORT)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if curl -s http://localhost:$FRONTEND_PORT > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 前端运行正常${NC}"
    echo "  地址: http://localhost:$FRONTEND_PORT"

    # 检查前端配置
    FRONTEND_ENV="/workspace/virtual_tutor/app_frontend/.env"
    if [ -f "$FRONTEND_ENV" ]; then
        if grep -q "REACT_APP_API_BASE_URL" "$FRONTEND_ENV"; then
            API_URL=$(grep "REACT_APP_API_BASE_URL" "$FRONTEND_ENV" | cut -d'=' -f2 | tr -d ' "'"'"'')
            echo -e "${GREEN}  ✓ API_BASE_URL 已配置: $API_URL${NC}"

            if echo "$API_URL" | grep -q ":$WEBSERVER_PORT"; then
                echo -e "${GREEN}  ✓ API_BASE_URL 端口正确${NC}"
            else
                echo -e "${YELLOW}  ! API_BASE_URL 端口可能不匹配${NC}"
                echo "    应该是: http://localhost:$WEBSERVER_PORT/api"
            fi
        else
            echo -e "${YELLOW}  ! REACT_APP_API_BASE_URL 未配置${NC}"
        fi
    else
        echo -e "${YELLOW}  ! .env 文件不存在: $FRONTEND_ENV${NC}"
    fi
else
    echo -e "${RED}✗ 前端未运行${NC}"
    echo "  启动命令:"
    echo "    cd /workspace/virtual_tutor/app_frontend"
    echo "    npm install  # 首次运行"
    echo "    npm start"
    ALL_OK=false
fi

echo ""

# 4. 端到端测试（如果所有服务都运行）
if [ "$ALL_OK" = true ]; then
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}[4/4] 端到端连接测试${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # 测试通过 Web Server 创建会话
    echo "正在测试会话创建..."

    # 注意：需要有效的 JWT token 才能测试
    # 这里只测试 GPU Server 的直接访问
    SESSION_RESPONSE=$(curl -s -X POST http://localhost:$GPUSERVER_PORT/v1/sessions \
      -H "Content-Type: application/json" \
      -d '{"tutor_id": 1, "student_id": 999}')

    if echo "$SESSION_RESPONSE" | grep -q "session_id"; then
        echo -e "${GREEN}✓ 会话创建成功${NC}"

        SESSION_ID=$(echo "$SESSION_RESPONSE" | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)
        ENGINE_URL=$(echo "$SESSION_RESPONSE" | grep -o '"engine_url":"[^"]*"' | cut -d'"' -f4)

        echo "  会话 ID: $SESSION_ID"
        echo "  WebSocket URL: $ENGINE_URL"

        # 清理测试会话
        curl -s -X DELETE http://localhost:$GPUSERVER_PORT/v1/sessions/$SESSION_ID > /dev/null 2>&1
        echo -e "${GREEN}  ✓ 测试会话已清理${NC}"
    else
        echo -e "${RED}✗ 会话创建失败${NC}"
        echo "  响应: $SESSION_RESPONSE"
    fi

    echo ""
fi

# 总结
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}连接状态总结${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}✓ 所有服务正常运行，前端可以正常连接！${NC}"
    echo ""
    echo "连接流程："
    echo "  1. 用户访问前端: http://localhost:$FRONTEND_PORT"
    echo "  2. 前端调用 Web Server API: http://localhost:$WEBSERVER_PORT/api"
    echo "  3. Web Server 调用 GPU Server: http://localhost:$GPUSERVER_PORT"
    echo "  4. GPU Server 返回 WebSocket URL: ws://localhost:$GPUSERVER_PORT/ws/ws/{session_id}"
    echo "  5. 前端直接连接 GPU Server WebSocket 进行实时对话"
    echo ""
    echo "测试步骤："
    echo "  1. 在浏览器打开: http://localhost:$FRONTEND_PORT"
    echo "  2. 登录系统"
    echo "  3. 选择一个导师开始对话"
    echo "  4. 打开浏览器开发者工具（F12）→ Network → WS"
    echo "  5. 应该能看到 WebSocket 连接到 GPU Server"
else
    echo -e "${RED}✗ 存在问题，请按照上述提示解决${NC}"
    echo ""
    echo "推荐启动顺序："
    echo "  1. 启动 GPU Server:"
    echo "     cd /workspace/gpuserver && ./start.sh"
    echo ""
    echo "  2. 启动 Web Server:"
    echo "     cd /workspace/virtual_tutor/app_backend"
    echo "     uvicorn app.main:app --host 0.0.0.0 --port $WEBSERVER_PORT"
    echo ""
    echo "  3. 启动前端:"
    echo "     cd /workspace/virtual_tutor/app_frontend"
    echo "     npm start"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "详细文档: cat FRONTEND_CONNECTION_GUIDE.md"
echo ""
