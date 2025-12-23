#!/bin/bash
#
# GPU Server - frpc 安装脚本（宿主机版本）
# 用途：在宿主机上安装 frpc，无需 Docker
#

set -e

echo "========================================="
echo "  frpc 安装脚本（宿主机版本）"
echo "========================================="
echo ""

# 配置变量
FRP_VERSION="0.56.0"
FRP_ARCH="linux_amd64"
FRP_URL="https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_${FRP_ARCH}.tar.gz"
INSTALL_DIR="/usr/local/frp"
CONFIG_DIR="$HOME/.frp"

# 检查权限
if [ "$EUID" -ne 0 ]; then
    echo "⚠️  建议使用 root 权限运行此脚本"
    echo "   或者安装到用户目录（需要修改 INSTALL_DIR）"
    read -p "是否继续？(y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    # 使用用户目录
    INSTALL_DIR="$HOME/frp"
fi

# 检查是否已安装
if [ -f "$INSTALL_DIR/frpc" ]; then
    echo "✅ frpc 已安装在 $INSTALL_DIR"
    $INSTALL_DIR/frpc --version
    echo ""
    read -p "是否重新安装？(y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "跳过安装"
        exit 0
    fi
fi

# 创建安装目录
echo "📁 创建安装目录: $INSTALL_DIR"
mkdir -p $INSTALL_DIR
mkdir -p $CONFIG_DIR

# 下载 frp
echo "⬇️  下载 frp ${FRP_VERSION}..."
cd $INSTALL_DIR
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

# 添加到 PATH（可选）
echo ""
echo "✅ frpc 安装成功！"
$INSTALL_DIR/frpc --version
echo ""
echo "📂 安装位置: $INSTALL_DIR"
echo "📂 配置目录: $CONFIG_DIR"
echo ""

# 询问是否添加到 PATH
read -p "是否添加到 PATH 环境变量？(y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # 检测 shell
    if [ -n "$ZSH_VERSION" ]; then
        RC_FILE="$HOME/.zshrc"
    else
        RC_FILE="$HOME/.bashrc"
    fi

    # 添加到 PATH
    if ! grep -q "$INSTALL_DIR" "$RC_FILE" 2>/dev/null; then
        echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$RC_FILE"
        echo "✅ 已添加到 $RC_FILE"
        echo "   请运行: source $RC_FILE"
    else
        echo "✅ PATH 已配置"
    fi
fi

# 复制配置文件模板
CONFIG_FILE="$CONFIG_DIR/frpc.ini"
if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "../frp_config/frpc.ini" ]; then
        cp ../frp_config/frpc.ini $CONFIG_FILE
        echo "📝 已复制配置文件到: $CONFIG_FILE"
    else
        echo "⚠️  未找到配置文件模板"
        echo "   请手动复制 frpc.ini 到 $CONFIG_FILE"
    fi
fi

echo ""
echo "========================================="
echo "  安装完成！"
echo "========================================="
echo ""
echo "📝 下一步："
echo "   1. 编辑配置文件: vim $CONFIG_FILE"
echo "      修改 server_addr 为 Web Server 的 IP"
echo ""
echo "   2. 启动 frpc:"
echo "      $INSTALL_DIR/frpc -c $CONFIG_FILE"
echo ""
echo "   3. 后台运行（推荐）:"
echo "      nohup $INSTALL_DIR/frpc -c $CONFIG_FILE > $CONFIG_DIR/frpc.log 2>&1 &"
echo ""
