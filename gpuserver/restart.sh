#!/bin/bash
# GPU Server 快速重启脚本
# 先停止服务，然后重新启动

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "重启 GPU Server..."
echo ""

# 停止服务
./stop.sh

# 等待一段时间确保端口释放
sleep 2

# 启动服务
./start.sh
