#!/bin/bash
#
# GPU Server - frp Client 安装和启动脚本
# 用途：在 GPU Server Docker 容器内运行，连接到 Web Server 的 frps
#

set -e

echo "========================================="
echo "  Virtual Tutor - frpc 安装脚本"
echo "  用途：在 GPU Server 上安装和启动 frp Client"
echo "========================================="
echo ""

# 配置变量
FRP_VERSION="0.56.0"
FRP_ARCH="linux_amd64"
FRP_URL="https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_${FRP_ARCH}.tar.gz"
INSTALL_DIR="/app/frp"
CONFIG_FILE="/app/frp_config/frpc.ini"

# 检查配置文件
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ 错误：找不到配置文件 $CONFIG_FILE"
    echo "请确保已将 frpc.ini 复制到容器中"
    exit 1
fi

# 检查是否已安装
if [ -f "$INSTALL_DIR/frpc" ]; then
    echo "✅ frpc 已安装，版本信息："
    $INSTALL_DIR/frpc --version
    echo ""
    read -p "是否重新安装？(y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "跳过安装，直接启动..."
        exec $INSTALL_DIR/frpc -c $CONFIG_FILE
    fi
fi

# 创建安装目录
echo "📁 创建安装目录..."
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# 下载 frp
echo "⬇️  下载 frp ${FRP_VERSION}..."
if command -v wget &> /dev/null; then
    wget -q --show-progress "$FRP_URL" -O frp.tar.gz
elif command -v curl &> /dev/null; then
    curl -L "$FRP_URL" -o frp.tar.gz --progress-bar
else
    echo "❌ 错误：需要 wget 或 curl 下载 frp"
    exit 1
fi

# 解压
echo "📦 解压 frp..."
tar -xzf frp.tar.gz --strip-components=1
rm -f frp.tar.gz

# 验证安装
if [ ! -f "$INSTALL_DIR/frpc" ]; then
    echo "❌ 错误：frpc 安装失败"
    exit 1
fi

echo "✅ frpc 安装成功！"
$INSTALL_DIR/frpc --version
echo ""

# 检查配置
echo "🔍 检查配置文件..."
SERVER_ADDR=$(grep "server_addr" $CONFIG_FILE | awk '{print $3}')
if [ "$SERVER_ADDR" = "YOUR_WEB_SERVER_IP" ]; then
    echo "⚠️  警告：配置文件中的 server_addr 未修改"
    echo "   请修改 $CONFIG_FILE 中的 server_addr 为实际的 Web Server IP"
    echo ""
    read -p "是否继续启动？(y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "已取消启动"
        exit 0
    fi
fi

# 启动 frpc
echo "🚀 启动 frpc..."
echo "   配置文件: $CONFIG_FILE"
echo "   Web Server: $SERVER_ADDR"
echo ""

# 使用 exec 替换当前进程，这样 Docker 容器会正确处理信号
exec $INSTALL_DIR/frpc -c $CONFIG_FILE
