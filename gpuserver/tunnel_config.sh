#!/bin/bash
# SSH 反向隧道配置文件
# 用于 GPU Server 连接到 Web Server

# ============================================
# Web Server 配置
# ============================================
# Web Server 的 SSH 连接信息
WEBSERVER_HOST="51.161.130.234"
WEBSERVER_SSH_PORT="22"
WEBSERVER_USER="root"  # 根据实际情况修改

# SSH 密钥路径（推荐使用密钥认证）
SSH_KEY_PATH="/root/.ssh/id_rsa"

# ============================================
# 端口映射配置
# ============================================
# GPU Server 本地端口 -> Web Server 暴露端口

# Management API: 本地 9000 -> Web Server 19000
LOCAL_MGMT_PORT="9000"
REMOTE_MGMT_PORT="19000"

# WebSocket: 本地 9001 -> Web Server 19001
LOCAL_WS_PORT="9001"
REMOTE_WS_PORT="19001"

# ============================================
# 隧道配置
# ============================================
# 心跳间隔（秒）
KEEPALIVE_INTERVAL=30

# 超时时间（秒）
KEEPALIVE_TIMEOUT=90

# 自动重连间隔（秒）
RECONNECT_INTERVAL=10

# 日志目录
LOG_DIR="/workspace/gpuserver/logs"
TUNNEL_LOG="${LOG_DIR}/ssh_tunnel.log"

# PID 文件
PID_DIR="/workspace/gpuserver/logs"
TUNNEL_PID="${PID_DIR}/ssh_tunnel.pid"
