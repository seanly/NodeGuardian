# NodeGuardian Python Architecture

## 概述

NodeGuardian现在支持Python脚本实现，所有hooks的trigger函数都调用Python脚本，配置统一从ConfigMap中加载。

## 架构设计

### 1. 配置管理

#### 统一配置加载器 (`config_loader.py`)
- 提供统一的配置加载接口
- 支持从ConfigMap和Secret加载配置
- 缓存配置以提高性能
- 支持配置热重载

```python
from config_loader import get_config, get_config_section, get_config_value

# 获取完整配置
config = get_config()

# 获取特定部分配置
email_config = get_config_section('email')

# 获取特定配置值
smtp_server = get_config_value('email', 'smtpServer', 'default')
```

#### 配置文件结构
```json
{
  "email": {
    "smtpServer": "smtp.gmail.com",
    "smtpPort": 587,
    "username": "",
    "password": "",
    "from": "nodeguardian@example.com",
    "to": ["admin@example.com"],
    "useTLS": true,
    "useSSL": false
  },
  "prometheus": {
    "url": "http://prometheus-k8s.monitoring.svc:9090",
    "timeout": "30s",
    "retries": 3,
    "queryTimeout": "60s",
    "maxSamples": 10000
  },
  "alert": {
    "webhookUrl": "",
    "defaultChannels": ["log", "email"],
    "retryAttempts": 3,
    "retryDelay": "5s",
    "batchSize": 10,
    "batchTimeout": "30s"
  },
  "monitoring": {
    "defaultCheckInterval": "30s",
    "defaultCooldownPeriod": "10m",
    "metricsServerUrl": "https://kubernetes.default.svc:443/apis/metrics.k8s.io/v1beta1",
    "maxConcurrentChecks": 10,
    "healthCheckInterval": "60s"
  },
  "log": {
    "level": "INFO",
    "format": "json",
    "output": "stdout",
    "maxSize": "100MB",
    "maxBackups": 3,
    "maxAge": "7d"
  },
  "node": {
    "defaultTaintKey": "nodeguardian.io/status",
    "defaultTaintEffect": "NoSchedule",
    "defaultLabelPrefix": "nodeguardian.io/",
    "excludeNamespaces": ["kube-system", "kube-public", "monitoring"],
    "maxEvictionPods": 10
  },
  "python": {
    "enabled": true,
    "scriptsPath": "/scripts",
    "logLevel": "INFO",
    "timeout": "300s",
    "maxRetries": 3
  }
}
```

### 2. Python脚本模块

#### 主控制器 (`nodeguardian_controller.py`)
- 处理NodeGuardianRule和AlertTemplate的CRD变化
- 管理规则生命周期
- 执行规则评估和动作

**主要功能：**
- 规则注册/注销
- 告警模板管理
- 节点指标获取
- 条件评估
- 动作执行（污点、告警、驱逐、标签、注解）

#### 告警管理器 (`alert_manager.py`)
- 处理告警模板渲染和发送
- 支持多种告警渠道（日志、邮件、Webhook）
- 模板化告警内容

**主要功能：**
- 告警模板管理
- 告警内容渲染
- 多渠道告警发送
- HTML邮件模板

#### 恢复管理器 (`recovery_manager.py`)
- 处理节点恢复逻辑
- 执行恢复动作
- 监控恢复条件

**主要功能：**
- 恢复条件检查
- 恢复动作执行（去污点、移除标签/注解、恢复告警）
- 恢复状态更新

### 3. Hook集成

所有Shell hooks现在都调用对应的Python脚本：

#### 主控制器Hook (`001-nodeguardian-controller.sh`)
```bash
hook::trigger() {
    # 初始化
    init::nodeguardian
    
    # 检查Python脚本是否存在
    local python_script="/scripts/nodeguardian_controller.py"
    if [[ ! -f "$python_script" ]]; then
        log::error "Python controller script not found: $python_script"
        exit 1
    fi
    
    # 检查Python是否可用
    if ! command -v python3 >/dev/null 2>&1; then
        log::error "Python3 not available, cannot run controller"
        exit 1
    fi
    
    log::info "Calling Python controller script"
    
    # 调用Python脚本
    if python3 "$python_script" "$@"; then
        log::info "Python controller script completed successfully"
    else
        log::error "Python controller script failed"
        exit 1
    fi
}
```

#### 告警管理器Hook (`002-alert-manager.sh`)
```bash
hook::trigger() {
    # 初始化
    init::nodeguardian
    
    # 检查Python脚本是否存在
    local python_script="/scripts/alert_manager.py"
    if [[ ! -f "$python_script" ]]; then
        log::error "Python alert manager script not found: $python_script"
        exit 1
    fi
    
    # 检查Python是否可用
    if ! command -v python3 >/dev/null 2>&1; then
        log::error "Python3 not available, cannot run alert manager"
        exit 1
    fi
    
    log::info "Calling Python alert manager script"
    
    # 调用Python脚本
    if python3 "$python_script" "$@"; then
        log::info "Python alert manager script completed successfully"
    else
        log::error "Python alert manager script failed"
        exit 1
    fi
}
```

#### 恢复管理器Hook (`003-recovery-manager.sh`)
```bash
hook::trigger() {
    # 初始化
    init::nodeguardian
    
    # 检查Python脚本是否存在
    local python_script="/scripts/recovery_manager.py"
    if [[ ! -f "$python_script" ]]; then
        log::error "Python recovery manager script not found: $python_script"
        exit 1
    fi
    
    # 检查Python是否可用
    if ! command -v python3 >/dev/null 2>&1; then
        log::error "Python3 not available, cannot run recovery manager"
        exit 1
    fi
    
    log::info "Calling Python recovery manager script"
    
    # 调用Python脚本
    if python3 "$python_script" "$@"; then
        log::info "Python recovery manager script completed successfully"
    else
        log::error "Python recovery manager script failed"
        exit 1
    fi
}
```

### 4. 部署配置

#### Dockerfile更新
```dockerfile
# 安装Python3和必要的包
RUN apk add --no-cache python3 py3-pip

# 复制Python脚本
COPY scripts/ /scripts/

# 设置执行权限
RUN chmod +x /scripts/nodeguardian_controller.py \
    && chmod +x /scripts/alert_manager.py \
    && chmod +x /scripts/recovery_manager.py \
    && chmod +x /scripts/config-manager.py \
    && chmod +x /scripts/config_loader.py
```

#### ConfigMap更新
- 添加了Python相关配置
- 支持Python脚本超时和重试配置
- 统一配置管理

## 使用方法

### 1. 构建镜像
```bash
docker build -t nodeguardian:latest -f deploy/Dockerfile .
```

### 2. 部署到Kubernetes
```bash
kubectl apply -f deploy/namespace.yaml
kubectl apply -f deploy/configmap.yaml
kubectl apply -f deploy/rbac.yaml
kubectl apply -f deploy/deployment.yaml
```

### 3. 运行集成测试
```bash
python3 scripts/test_integration.py
```

## 优势

1. **统一配置管理**：所有配置都从ConfigMap加载，便于管理
2. **Python生态**：可以利用丰富的Python库和工具
3. **更好的错误处理**：Python提供更强大的异常处理机制
4. **代码复用**：配置加载器可以在所有脚本中复用
5. **易于测试**：Python脚本更容易进行单元测试
6. **向后兼容**：Shell hooks仍然存在，只是调用Python脚本

## 注意事项

1. 确保Python3在容器中可用
2. 所有Python脚本都需要执行权限
3. 配置文件路径必须正确
4. Secret文件需要正确挂载
5. 日志级别可以通过配置调整

## 故障排除

### 常见问题

1. **Python脚本找不到**
   - 检查脚本是否被正确复制到容器中
   - 检查执行权限是否正确设置

2. **配置加载失败**
   - 检查ConfigMap是否正确挂载
   - 检查配置文件路径是否正确

3. **Secret加载失败**
   - 检查Secret是否正确创建
   - 检查Secret挂载路径是否正确

### 调试方法

1. 查看容器日志
2. 运行集成测试脚本
3. 检查配置文件内容
4. 验证Python脚本语法
