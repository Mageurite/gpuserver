#!/bin/bash

# Avatar 功能测试脚本

echo "=========================================="
echo "  Avatar (MuseTalk) 功能测试"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# API 地址
API_BASE="http://localhost:9000"

# 1. 健康检查
echo -e "${BLUE}[1/5] 健康检查...${NC}"
HEALTH=$(curl -s "${API_BASE}/health")
if echo "$HEALTH" | grep -q "healthy"; then
    echo -e "${GREEN}✓ GPU Server 运行正常${NC}"
else
    echo -e "${RED}✗ GPU Server 未运行${NC}"
    exit 1
fi
echo ""

# 2. 检查配置
echo -e "${BLUE}[2/5] 检查 Avatar 配置...${NC}"
if [ -f ".env" ]; then
    ENABLE_AVATAR=$(grep "^ENABLE_AVATAR=" .env | cut -d'=' -f2)
    MUSETALK_BASE=$(grep "^MUSETALK_BASE=" .env | cut -d'=' -f2)
    MUSETALK_CONDA=$(grep "^MUSETALK_CONDA_ENV=" .env | cut -d'=' -f2)

    echo "  ENABLE_AVATAR: $ENABLE_AVATAR"
    echo "  MUSETALK_BASE: $MUSETALK_BASE"
    echo "  MUSETALK_CONDA_ENV: $MUSETALK_CONDA"

    if [ "$ENABLE_AVATAR" = "true" ]; then
        echo -e "${GREEN}✓ 真实 MuseTalk 已启用${NC}"
    else
        echo -e "${YELLOW}! Mock 模式已启用${NC}"
    fi
else
    echo -e "${RED}✗ .env 文件不存在${NC}"
    exit 1
fi
echo ""

# 3. 检查 MuseTalk 环境
echo -e "${BLUE}[3/5] 检查 MuseTalk 环境...${NC}"
if [ -f "$MUSETALK_BASE/inference.sh" ]; then
    echo -e "${GREEN}✓ MuseTalk inference.sh 存在${NC}"
else
    echo -e "${RED}✗ MuseTalk inference.sh 不存在${NC}"
fi

if [ -d "$MUSETALK_CONDA" ]; then
    echo -e "${GREEN}✓ MuseTalk Conda 环境存在${NC}"
else
    echo -e "${RED}✗ MuseTalk Conda 环境不存在${NC}"
fi
echo ""

# 4. 列出现有 Avatar
echo -e "${BLUE}[4/5] 列出现有 Avatar...${NC}"
AVATARS=$(curl -s "${API_BASE}/v1/avatars")
echo "$AVATARS" | python3 -m json.tool 2>/dev/null || echo "$AVATARS"
echo ""

# 5. 查看测试视频
echo -e "${BLUE}[5/5] 测试视频检查...${NC}"
TEST_VIDEO="/workspace/MuseTalk/data/video/yongen.mp4"
if [ -f "$TEST_VIDEO" ]; then
    echo -e "${GREEN}✓ 测试视频存在: $TEST_VIDEO${NC}"
    ls -lh "$TEST_VIDEO"
else
    echo -e "${YELLOW}! 测试视频不存在: $TEST_VIDEO${NC}"
fi
echo ""

echo "=========================================="
echo -e "${GREEN}测试完成${NC}"
echo "=========================================="
echo ""
echo "使用示例:"
echo ""
echo "1. 从文件路径创建 Avatar:"
echo "   curl -X POST '${API_BASE}/v1/avatars/create' \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"avatar_id\":\"test_avatar\",\"video_path\":\"$TEST_VIDEO\"}'"
echo ""
echo "2. 上传视频创建 Avatar:"
echo "   curl -X POST '${API_BASE}/v1/avatars/upload' \\"
echo "     -F 'avatar_id=test_avatar' \\"
echo "     -F 'video_file=@/path/to/video.mp4'"
echo ""
echo "3. 查看 Avatar:"
echo "   curl '${API_BASE}/v1/avatars/test_avatar'"
echo ""
