# NodeGuardian Shell-Operator Dockerfile
# 基于shell-operator构建NodeGuardian镜像

FROM flant/shell-operator:latest

# 安装Python3和必要的包
RUN apk add --no-cache python3 py3-pip

# 设置工作目录
WORKDIR /hooks

# 复制公共函数库
COPY hooks/common/ /hooks/common/

# 复制所有hooks
COPY hooks/001-nodeguardian-controller.sh /hooks/001-nodeguardian-controller.sh
COPY hooks/002-alert-manager.sh /hooks/002-alert-manager.sh
COPY hooks/003-recovery-manager.sh /hooks/003-recovery-manager.sh

# 复制Python脚本
COPY scripts/ /scripts/

# 设置执行权限
RUN chmod +x /hooks/001-nodeguardian-controller.sh \
    && chmod +x /hooks/002-alert-manager.sh \
    && chmod +x /hooks/003-recovery-manager.sh \
    && chmod +x /hooks/common/functions.sh \
    && chmod +x /scripts/sendmail.py \
    && chmod +x /scripts/nodeguardian_controller.py \
    && chmod +x /scripts/alert_manager.py \
    && chmod +x /scripts/recovery_manager.py \
    && chmod +x /scripts/config-manager.py \
    && chmod +x /scripts/config_loader.py

# 创建必要的目录
RUN mkdir -p /tmp/nodeguardian/cooldown \
    && mkdir -p /tmp/nodeguardian/state \
    && mkdir -p /tmp/nodeguardian/rules \
    && mkdir -p /tmp/nodeguardian/templates

# 设置环境变量
ENV LOG_LEVEL=INFO
ENV NODEGUARDIAN_NAMESPACE=nodeguardian-system
ENV PROMETHEUS_URL=http://prometheus-k8s.monitoring.svc:9090
ENV METRICS_SERVER_URL=https://kubernetes.default.svc:443/apis/metrics.k8s.io/v1beta1

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "shell-operator" > /dev/null || exit 1

# 标签
LABEL maintainer="NodeGuardian Team"
LABEL description="NodeGuardian: Event-driven Kubernetes Node Self-healing Tool"
LABEL version="1.0.0"