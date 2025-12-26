#!/bin/bash
# GPU Server 快速重启脚本（包含 FRP）
# 先停止所有服务，然后重新启动

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "=========================================="
echo "  重启所有服务（GPU Server + FRP）"
echo "=========================================="
echo ""

# 停止所有服务
echo -e "${BLUE}正在停止所有服务...${NC}"
./stop_all.sh

# 等待一段时间确保端口释放
echo ""
echo -e "${YELLOW}等待 3 秒确保端口释放...${NC}"
sleep 3

# 启动所有服务
echo ""
echo -e "${BLUE}正在启动所有服务...${NC}"
echo ""
./start_all.sh

echo ""
echo "=========================================="
echo -e "${GREEN}  重启完成！${NC}"
echo "=========================================="
echo ""
