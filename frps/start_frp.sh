#!/bin/bash

# ================= 配置区域 =================
# 定义 frpc 程序所在的【绝对路径】
# 根据你之前的路径：/workspace/frps/frp_0.66.0_linux_amd64
FRP_DIR="/workspace/frps/frp_0.66.0_linux_amd64"

# 定义会话名称
SESSION_NAME="frpc_bg"
# ===========================================

# 1. 检查 screen 是否安装
if ! command -v screen &> /dev/null; then
    echo "❌ 错误: 未找到 screen 命令。"
    echo "💡 请尝试安装: apt-get update && apt-get install -y screen"
    exit 1
fi

# 2. 检查目标目录是否存在
if [ ! -d "$FRP_DIR" ]; then
    echo "❌ 错误: 找不到目录 $FRP_DIR"
    echo "   请检查脚本中的 FRP_DIR 配置路径是否正确。"
    exit 1
fi

# 3. 进入目标目录 (这是关键，确保能找到 frpc.toml)
cd "$FRP_DIR" || { echo "❌ 无法进入目录 $FRP_DIR"; exit 1; }

# 4. 如果有旧会话，先杀掉
if screen -list | grep -q "$SESSION_NAME"; then
    echo "🔄 发现旧的 $SESSION_NAME 会话，正在停止..."
    screen -X -S $SESSION_NAME quit
fi

# 5. 启动 screen
# 因为已经 cd 到了目录里，所以直接用 ./frpc
screen -dmS $SESSION_NAME ./frpc -c ./frpc.toml

# 6. 检查状态
sleep 1
if screen -list | grep -q "$SESSION_NAME"; then
    echo "✅ FRPC 启动成功！"
    echo "📂 运行目录: $(pwd)"
    echo "----------------------------------------"
    echo "👀 查看后台: screen -r $SESSION_NAME"
    echo "⌨️  退出查看: 按 Ctrl+A 然后按 D (切勿按 Ctrl+C)"
    echo "🛑 停止服务: screen -X -S $SESSION_NAME quit"
    echo "----------------------------------------"
else
    echo "❌ 启动失败。"
    echo "👉 请尝试手动运行: cd $FRP_DIR && ./frpc -c ./frpc.toml 查看报错"
fi