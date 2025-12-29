#!/bin/bash
#
# GPU Server 统一启动/停止脚本
# 使用方法:
#   ./server.sh start   - 启动服务
#   ./server.sh stop    - 停止服务
#   ./server.sh restart - 重启服务
#   ./server.sh status  - 查看状态
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/logs/server.pid"
LOG_FILE="$SCRIPT_DIR/logs/unified_server.log"

# 确保日志目录存在
mkdir -p logs

# 检测 Python 环境
detect_python() {
    # 优先使用 mt 环境（支持视频生成）
    if [ -f "/workspace/conda_envs/mt/bin/python" ]; then
        echo "/workspace/conda_envs/mt/bin/python"
    elif [ -f "/workspace/conda_envs/rag/bin/python" ]; then
        echo "/workspace/conda_envs/rag/bin/python"
    else
        echo "python3"
    fi
}

start_server() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "✗ GPU Server 已在运行 (PID: $PID)"
            return 1
        fi
    fi

    PYTHON_BIN=$(detect_python)
    echo "使用 Python: $PYTHON_BIN"
    echo "启动 GPU Server..."

    nohup "$PYTHON_BIN" unified_server.py > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"

    sleep 2

    if ps -p "$PID" > /dev/null 2>&1; then
        echo "✓ GPU Server 启动成功 (PID: $PID)"
        echo "  日志: $LOG_FILE"
        echo "  健康检查: curl http://localhost:9000/health"
    else
        echo "✗ GPU Server 启动失败"
        echo "  查看日志: tail -f $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop_server() {
    if [ ! -f "$PID_FILE" ]; then
        echo "✗ GPU Server 未运行"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "✗ GPU Server 未运行"
        rm -f "$PID_FILE"
        return 1
    fi

    echo "停止 GPU Server (PID: $PID)..."
    kill "$PID"

    # 等待进程结束
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    # 如果还没停止，强制杀死
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "强制停止..."
        kill -9 "$PID"
    fi

    rm -f "$PID_FILE"
    echo "✓ GPU Server 已停止"
}

status_server() {
    if [ ! -f "$PID_FILE" ]; then
        echo "✗ GPU Server 未运行"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "✓ GPU Server 运行中 (PID: $PID)"

        # 尝试健康检查
        if command -v curl > /dev/null 2>&1; then
            echo ""
            echo "健康检查:"
            curl -s http://localhost:9000/health || echo "  无法连接"
        fi
    else
        echo "✗ GPU Server 未运行 (PID 文件存在但进程不存在)"
        rm -f "$PID_FILE"
        return 1
    fi
}

case "${1:-}" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server || true
        sleep 1
        start_server
        ;;
    status)
        status_server
        ;;
    *)
        echo "使用方法: $0 {start|stop|restart|status}"
        echo ""
        echo "  start   - 启动 GPU Server"
        echo "  stop    - 停止 GPU Server"
        echo "  restart - 重启 GPU Server"
        echo "  status  - 查看运行状态"
        exit 1
        ;;
esac
