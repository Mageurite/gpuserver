# GPU Server Docker 部署配置（frp 反向隧道方案 - 容器内运行）

FROM python:3.10-slim

WORKDIR /app

# ============================================
# 安装系统依赖
# ============================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ============================================
# 安装 frp client（在构建时直接安装）
# ============================================
RUN wget -q https://github.com/fatedier/frp/releases/download/v0.56.0/frp_0.56.0_linux_amd64.tar.gz && \
    tar -xzf frp_0.56.0_linux_amd64.tar.gz && \
    mv frp_0.56.0_linux_amd64/frpc /usr/local/bin/ && \
    chmod +x /usr/local/bin/frpc && \
    rm -rf frp_0.56.0_linux_amd64*

# 创建 frp 配置目录
RUN mkdir -p /opt/frp

# ============================================
# 安装 Python 依赖
# ============================================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ============================================
# 复制应用代码
# ============================================
COPY server.py .
COPY config.py .
COPY session_manager.py .
COPY ai_models.py .
COPY .env .

# ============================================
# 复制 frp 配置和启动脚本
# ============================================
# frpc 配置文件（构建时复制）
COPY frpc.ini /opt/frp/frpc.ini

# 统一启动脚本（先启动 frpc，再启动应用）
COPY docker_entrypoint.sh /docker_entrypoint.sh
RUN chmod +x /docker_entrypoint.sh

# 创建日志目录
RUN mkdir -p logs

# ============================================
# 暴露端口
# ============================================
EXPOSE 9000 9001

# ============================================
# 健康检查
# ============================================
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:9000/health')"

# ============================================
# 启动服务（使用统一入口脚本）
# ============================================
ENTRYPOINT ["/docker_entrypoint.sh"]
CMD ["python", "-u", "server.py"]
