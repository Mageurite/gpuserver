#!/bin/bash
#
# GPU Server FRP Client 安装脚本
# 用于在 GPU Server (容器内) 安装和配置 frpc
#

set -e

VERSION="0.58.1"
INSTALL_DIR="/opt/frp"
CONFIG_DIR="/etc/frp"
LOG_DIR="/var/log/frp"
SERVER_ADDR="51.161.130.234"
SERVER_PORT="7000"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=========================================="
echo "GPU Server FRP Client 安装脚本"
echo -e "==========================================${NC}\n"

# 检查是否已安装
if [ -f "${INSTALL_DIR}/frpc" ]; then
    echo -e "${YELLOW}FRP Client 已安装${NC}"
    read -p "是否重新安装? (y/n): " REINSTALL
    if [ "$REINSTALL" != "y" ]; then
        echo "跳过安装"
        exit 0
    fi
fi

# 提示输入 token
echo -e "${YELLOW}请从 Web Server 获取 Token${NC}"
echo "在 Web Server 上运行: sudo cat /etc/frp/token.txt"
echo ""
read -p "请输入 Token: " TOKEN

if [ -z "$TOKEN" ]; then
    echo -e "${RED}错误: Token 不能为空${NC}"
    exit 1
fi

# 下载 FRP
echo -e "\n${GREEN}1. 下载 FRP v${VERSION}...${NC}"
cd /tmp
if [ ! -f "frp_${VERSION}_linux_amd64.tar.gz" ]; then
    wget -q --show-progress https://github.com/fatedier/frp/releases/download/v${VERSION}/frp_${VERSION}_linux_amd64.tar.gz
else
    echo "  安装包已存在，跳过下载"
fi

tar -xzf frp_${VERSION}_linux_amd64.tar.gz

# 安装
echo -e "\n${GREEN}2. 安装 frpc 到 ${INSTALL_DIR}...${NC}"
mkdir -p ${INSTALL_DIR}
cp frp_${VERSION}_linux_amd64/frpc ${INSTALL_DIR}/
chmod +x ${INSTALL_DIR}/frpc

# 创建目录
echo -e "\n${GREEN}3. 创建配置和日志目录...${NC}"
mkdir -p ${CONFIG_DIR} ${LOG_DIR}

# 创建配置
echo -e "\n${GREEN}4. 创建配置文件...${NC}"
cat > ${CONFIG_DIR}/frpc.toml <<EOF
# FRP Client 配置
[common]
# FRP 服务端地址
server_addr = "$SERVER_ADDR"
server_port = $SERVER_PORT

# 身份验证
authentication_method = "token"
token = "$TOKEN"

# 日志配置
log_file = "${LOG_DIR}/frpc.log"
log_level = "info"
log_max_days = 7

# GPU Management API 代理
[gpu-api]
type = "tcp"
local_ip = "127.0.0.1"
local_port = 9000
remote_port = 9000

# 健康检查
health_check_type = "tcp"
health_check_timeout_s = 3
health_check_max_failed = 3
health_check_interval_s = 10

# 性能优化
use_compression = true
EOF

chmod 600 ${CONFIG_DIR}/frpc.toml

# 检查是否支持 systemd
echo -e "\n${GREEN}5. 配置启动方式...${NC}"
if command -v systemctl &> /dev/null && [ -d /run/systemd/system ]; then
    # 使用 systemd
    echo "  检测到 systemd，创建服务..."

    cat > /etc/systemd/system/frpc.service <<'SEOF'
[Unit]
Description=FRP Client Service
After=network.target

[Service]
Type=simple
User=root
Restart=always
RestartSec=10
ExecStart=/opt/frp/frpc -c /etc/frp/frpc.toml
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SEOF

    systemctl daemon-reload
    systemctl start frpc
    systemctl enable frpc

    echo -e "${GREEN}✓ FRP Client 已通过 systemd 启动${NC}"
    echo "  检查状态: systemctl status frpc"
    echo "  查看日志: journalctl -u frpc -f"
else
    # 手动启动
    echo "  未检测到 systemd，使用手动启动..."

    # 停止旧进程
    pkill -f "frpc -c" || true

    # 启动
    nohup ${INSTALL_DIR}/frpc -c ${CONFIG_DIR}/frpc.toml > ${LOG_DIR}/frpc.log 2>&1 &
    FRPC_PID=$!
    echo $FRPC_PID > /var/run/frpc.pid

    echo -e "${GREEN}✓ FRP Client 已手动启动 (PID: $FRPC_PID)${NC}"
    echo "  停止: kill \$(cat /var/run/frpc.pid)"
fi

# 等待连接
echo -e "\n${GREEN}6. 等待连接到 FRP Server...${NC}"
sleep 3

# 检查日志
if [ -f "${LOG_DIR}/frpc.log" ]; then
    if grep -q "start proxy success" ${LOG_DIR}/frpc.log; then
        echo -e "${GREEN}✓ 连接成功！${NC}"
    else
        echo -e "${YELLOW}⚠ 请检查日志确认连接状态${NC}"
    fi

    echo -e "\n${YELLOW}最近的日志:${NC}"
    tail -10 ${LOG_DIR}/frpc.log
fi

echo -e "\n${GREEN}=========================================="
echo "安装完成"
echo -e "==========================================${NC}\n"

echo "配置信息:"
echo "  FRP Server: $SERVER_ADDR:$SERVER_PORT"
echo "  本地服务: localhost:9000"
echo "  远程端口: 9000"
echo ""
echo "查看日志:"
echo "  tail -f ${LOG_DIR}/frpc.log"
echo ""
echo "测试连接 (在 Web Server 上运行):"
echo "  curl http://localhost:9000/health"
echo ""
