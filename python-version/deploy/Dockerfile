FROM flant/shell-operator:latest

# 安装Python和必要的工具
USER root
RUN apk add --no-cache \
    python3 \
    python3-dev \
    py3-pip \
    curl \
    jq \
    bc \
    mailutils \
    bash \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev

# 安装uv (Python包管理器)
RUN pip3 install uv

# 复制Python项目文件
COPY pyproject.toml /app/
COPY src/ /app/src/
COPY hooks/ /app/hooks/

# 设置工作目录
WORKDIR /app

# 安装Python依赖
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install -e .

# 复制CRD定义
COPY ../crd/ /hooks/crd/

# 设置权限
RUN chmod +x /app/hooks/*.py
RUN chmod +x /hooks/crd/*.yaml

# 创建必要的目录
RUN mkdir -p /tmp/nodeguardian/{rules,templates,cooldown,state,metrics}

# 切换回非root用户
USER 65534:65534

# 设置环境变量
ENV SHELL_OPERATOR_HOOKS_DIR=/app/hooks
ENV PYTHONPATH=/app/src
ENV NODEGUARDIAN_NAMESPACE=nodeguardian-system
ENV LOG_LEVEL=INFO
ENV PROMETHEUS_URL=http://prometheus-k8s.monitoring.svc:9090
ENV METRICS_SERVER_URL=https://kubernetes.default.svc:443/apis/metrics.k8s.io/v1beta1

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9115/health || exit 1
