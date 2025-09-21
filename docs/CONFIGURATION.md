# NodeGuardian 配置管理指南

## 概述

NodeGuardian使用统一的JSON配置文件来管理所有组件配置，包括邮件、Prometheus、告警、监控等设置。配置文件通过Kubernetes ConfigMap和Secret进行管理。

## 配置文件结构

### 统一配置文件 (config.json)

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
  }
}
```

## 配置项说明

### 邮件配置 (email)

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| smtpServer | string | 是 | SMTP服务器地址 |
| smtpPort | integer | 否 | SMTP端口 (默认587) |
| username | string | 否 | SMTP用户名 |
| password | string | 否 | SMTP密码 |
| from | string | 是 | 发件人邮箱 |
| to | array | 是 | 收件人邮箱列表 |
| useTLS | boolean | 否 | 使用TLS (默认true) |
| useSSL | boolean | 否 | 使用SSL (默认false) |

### Prometheus配置 (prometheus)

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| url | string | 是 | Prometheus服务器URL |
| timeout | string | 否 | 请求超时时间 (默认30s) |
| retries | integer | 否 | 重试次数 (默认3) |
| queryTimeout | string | 否 | 查询超时时间 (默认60s) |
| maxSamples | integer | 否 | 最大样本数 (默认10000) |

### 告警配置 (alert)

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| webhookUrl | string | 否 | 默认Webhook URL |
| defaultChannels | array | 否 | 默认告警渠道 (默认["log", "email"]) |
| retryAttempts | integer | 否 | 重试次数 (默认3) |
| retryDelay | string | 否 | 重试延迟 (默认5s) |
| batchSize | integer | 否 | 批处理大小 (默认10) |
| batchTimeout | string | 否 | 批处理超时 (默认30s) |

### 监控配置 (monitoring)

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| defaultCheckInterval | string | 否 | 默认检查间隔 (默认30s) |
| defaultCooldownPeriod | string | 否 | 默认冷却期 (默认10m) |
| metricsServerUrl | string | 否 | Metrics Server URL |
| maxConcurrentChecks | integer | 否 | 最大并发检查数 (默认10) |
| healthCheckInterval | string | 否 | 健康检查间隔 (默认60s) |

### 日志配置 (log)

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| level | string | 否 | 日志级别 (默认INFO) |
| format | string | 否 | 日志格式 (默认json) |
| output | string | 否 | 输出目标 (默认stdout) |
| maxSize | string | 否 | 最大文件大小 (默认100MB) |
| maxBackups | integer | 否 | 最大备份数 (默认3) |
| maxAge | string | 否 | 最大保存时间 (默认7d) |

### 节点配置 (node)

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| defaultTaintKey | string | 否 | 默认污点键 (默认nodeguardian.io/status) |
| defaultTaintEffect | string | 否 | 默认污点效果 (默认NoSchedule) |
| defaultLabelPrefix | string | 否 | 默认标签前缀 (默认nodeguardian.io/) |
| excludeNamespaces | array | 否 | 排除的命名空间 |
| maxEvictionPods | integer | 否 | 最大驱逐Pod数 (默认10) |

## 配置管理工具

NodeGuardian提供了配置管理工具 `config-manager.py`，用于管理配置文件。

### 基本用法

```bash
# 初始化配置文件
python3 scripts/config-manager.py init --output config.json

# 更新配置项
python3 scripts/config-manager.py update --section email --key smtpServer --value "smtp.company.com"

# 获取配置项
python3 scripts/config-manager.py get --section email --key smtpServer

# 验证配置
python3 scripts/config-manager.py validate --config config.json

# 生成Kubernetes资源
python3 scripts/config-manager.py k8s --config config.json --output k8s-resources.yaml
```

### 高级用法

```bash
# 更新嵌套配置项
python3 scripts/config-manager.py update --section email --key "to[0]" --value "admin@company.com"

# 生成包含Secret的Kubernetes资源
python3 scripts/config-manager.py k8s --config config.json --secrets secrets.json --output k8s-resources.yaml
```

## Kubernetes部署

### 1. 创建ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: nodeguardian-config
  namespace: nodeguardian-system
data:
  config.json: |
    {
      "email": {
        "smtpServer": "smtp.gmail.com",
        "smtpPort": 587,
        "from": "nodeguardian@example.com",
        "to": ["admin@example.com"],
        "useTLS": true
      },
      "prometheus": {
        "url": "http://prometheus-k8s.monitoring.svc:9090"
      }
    }
```

### 2. 创建Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: nodeguardian-secrets
  namespace: nodeguardian-system
type: Opaque
data:
  email-username: dXNlckBleGFtcGxlLmNvbQ==  # base64编码
  email-password: cGFzc3dvcmQ=              # base64编码
  webhook-url: aHR0cHM6Ly93ZWJob29rLmV4YW1wbGUuY29t  # base64编码
```

### 3. 挂载到Pod

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nodeguardian
spec:
  template:
    spec:
      containers:
      - name: nodeguardian
        volumeMounts:
        - name: config
          mountPath: /etc/nodeguardian/config
          readOnly: true
        - name: secrets
          mountPath: /etc/nodeguardian/secrets
          readOnly: true
      volumes:
      - name: config
        configMap:
          name: nodeguardian-config
      - name: secrets
        secret:
          secretName: nodeguardian-secrets
```

## 配置优先级

NodeGuardian按以下优先级加载配置：

1. **规则级配置**: NodeGuardianRule中指定的配置
2. **ConfigMap配置**: 统一配置文件中的设置
3. **环境变量**: 向后兼容的环境变量
4. **默认配置**: 内置的默认值

## 常见配置示例

### Gmail配置

```json
{
  "email": {
    "smtpServer": "smtp.gmail.com",
    "smtpPort": 587,
    "from": "nodeguardian@yourdomain.com",
    "to": ["admin@yourdomain.com"],
    "useTLS": true,
    "useSSL": false
  }
}
```

### 企业邮箱配置

```json
{
  "email": {
    "smtpServer": "mail.company.com",
    "smtpPort": 465,
    "from": "alerts@company.com",
    "to": ["ops@company.com", "admin@company.com"],
    "useTLS": false,
    "useSSL": true
  }
}
```

### 自定义Prometheus配置

```json
{
  "prometheus": {
    "url": "http://prometheus.company.com:9090",
    "timeout": "60s",
    "retries": 5,
    "queryTimeout": "120s",
    "maxSamples": 50000
  }
}
```

## 故障排除

### 配置验证

```bash
# 验证配置文件语法
python3 scripts/config-manager.py validate --config config.json

# 检查配置加载
kubectl exec -it deployment/nodeguardian -- cat /etc/nodeguardian/config/config.json
```

### 常见问题

1. **配置文件格式错误**
   - 使用JSON验证工具检查语法
   - 确保所有字符串用双引号包围

2. **Secret配置问题**
   - 确保Secret中的值是base64编码
   - 检查Secret是否正确挂载

3. **配置不生效**
   - 重启Pod以重新加载配置
   - 检查ConfigMap和Secret是否正确创建

## 最佳实践

1. **敏感信息管理**
   - 将密码、API密钥等敏感信息存储在Secret中
   - 使用base64编码存储敏感数据

2. **配置版本控制**
   - 将配置文件纳入版本控制
   - 使用配置管理工具管理配置变更

3. **环境隔离**
   - 为不同环境创建不同的ConfigMap
   - 使用命名空间隔离配置

4. **配置验证**
   - 部署前验证配置文件
   - 使用配置管理工具进行验证
