# NodeGuardian Python版本

> 基于shell-operator和Python的事件驱动Kubernetes节点自愈工具

NodeGuardian Python版本是一个基于shell-operator和Python实现的Kubernetes节点监控和自愈工具，通过CRD规则引擎实现条件触发、动作执行和智能告警。

## 🚀 特性

- ✅ **Python实现**：使用Python实现核心逻辑，更易维护和扩展
- ✅ **结构化日志**：使用structlog提供结构化日志记录
- ✅ **类型安全**：使用Pydantic和类型注解确保代码质量
- ✅ **异步支持**：支持异步操作，提高性能
- ✅ **规则驱动**：通过 `NodeGuardianRule` CRD 定义监控规则
- ✅ **条件触发**：支持多条件组合，灵活定义触发逻辑
- ✅ **动作执行**：支持多种处理动作（污点、告警、驱逐等）
- ✅ **定期监控**：基于规则配置的 `checkInterval` 定期检查节点指标
- ✅ **事件响应**：规则变化时立即生效，支持实时配置更新
- ✅ **智能告警**：支持多种告警渠道和模板化告警内容
- ✅ **自动恢复**：支持恢复条件检测和自动恢复动作

## 📋 系统要求

- Kubernetes 1.16+
- shell-operator
- Python 3.9+
- Prometheus (可选，用于指标收集)
- Metrics Server (可选，用于基础指标)

## 🛠️ 安装部署

### 快速部署

```bash
# 进入Python版本目录
cd python-version

# 完整部署
./deploy.sh --full

# 或者分步部署
./deploy.sh --build --deploy --examples --verify
```

### 手动部署

```bash
# 1. 部署CRD
kubectl apply -f ../crd/

# 2. 部署命名空间和RBAC
kubectl apply -f ../deploy/namespace.yaml
kubectl apply -f ../deploy/rbac.yaml

# 3. 构建并部署应用
docker build -t nodeguardian-python:latest -f deploy/Dockerfile .
kubectl apply -f deploy/deployment.yaml

# 4. 部署示例
kubectl apply -f ../examples/
```

## 🐍 Python开发

### 项目结构

```
python-version/
├── src/nodeguardian/          # Python包源码
│   ├── __init__.py
│   ├── common.py              # 公共工具和配置
│   ├── rule_engine.py         # 规则引擎
│   └── alert_manager.py       # 告警管理器
├── hooks/                     # Shell-operator hooks
│   └── nodeguardian_controller.py
├── deploy/                    # 部署配置
│   ├── Dockerfile
│   └── deployment.yaml
├── examples/                  # 使用示例
├── tests/                     # 测试文件
├── pyproject.toml            # Python项目配置
└── deploy.sh                 # 部署脚本
```

### 开发环境设置

```bash
# 安装uv (Python包管理器)
pip install uv

# 创建虚拟环境
uv venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
uv pip install -e .

# 安装开发依赖
uv pip install -e ".[dev]"
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_rule_engine.py

# 运行测试并生成覆盖率报告
pytest --cov=src/nodeguardian --cov-report=html
```

### 代码质量检查

```bash
# 代码格式化
black src/ hooks/ tests/

# 导入排序
isort src/ hooks/ tests/

# 类型检查
mypy src/

# 代码检查
flake8 src/ hooks/ tests/
```

## 📖 使用指南

### 创建监控规则

```yaml
apiVersion: nodeguardian.k8s.io/v1
kind: NodeGuardianRule
metadata:
  name: high-load-isolation
spec:
  # 触发条件
  conditions:
    - metric: "cpuLoadRatio"
      operator: "GreaterThan"
      value: 1.5
      duration: "3m"
    - metric: "memoryUtilizationPercent"
      operator: "GreaterThan"
      value: 90
      duration: "2m"
  
  conditionLogic: "AND"
  
  # 目标节点
  nodeSelector:
    matchLabels:
      node-role.kubernetes.io/worker: "true"
  
  # 执行动作
  actions:
    - type: "taint"
      taint:
        key: "nodeguardian/high-load"
        value: "true"
        effect: "NoSchedule"
    - type: "alert"
      alert:
        template: "high-load-alert"
        channels: ["email", "slack"]
  
  # 监控配置
  monitoring:
    checkInterval: "30s"
    cooldownPeriod: "10m"
  
  # 规则元数据
  metadata:
    priority: 100
    enabled: true
    description: "高负载节点自动隔离规则"
```

### 创建告警模板

```yaml
apiVersion: nodeguardian.k8s.io/v1
kind: AlertTemplate
metadata:
  name: high-load-alert
spec:
  subject: "[NodeGuardian] 节点高负载告警"
  body: |
    节点 {{ node_name }} 触发高负载规则：
    
    当前指标：
    - CPU负载率: {{ metrics.cpu_load_ratio }}
    - 内存使用率: {{ metrics.memory_utilization }}%
    - 检查时间: {{ timestamp }}
    
    请及时处理。
  channels: ["email", "slack", "webhook"]
```

## 🔧 配置说明

### 环境变量

| 变量名 | 默认值 | 描述 |
|--------|--------|------|
| `NODEGUARDIAN_NAMESPACE` | `nodeguardian-system` | 部署命名空间 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `PROMETHEUS_URL` | `http://prometheus-k8s.monitoring.svc:9090` | Prometheus地址 |
| `METRICS_SERVER_URL` | `https://kubernetes.default.svc:443/apis/metrics.k8s.io/v1beta1` | Metrics Server地址 |
| `ALERT_EMAIL_TO` | `admin@example.com` | 邮件告警收件人 |
| `ALERT_SLACK_WEBHOOK` | `` | Slack Webhook地址 |
| `ALERT_WEBHOOK_URL` | `` | 自定义Webhook地址 |

### 支持的指标类型

- `cpuUtilizationPercent`: CPU使用率百分比
- `memoryUtilizationPercent`: 内存使用率百分比
- `diskUtilizationPercent`: 磁盘使用率百分比
- `cpuLoadRatio`: CPU负载率

### 支持的操作符

- `GreaterThan`: 大于
- `LessThan`: 小于
- `EqualTo`: 等于
- `NotEqualTo`: 不等于
- `GreaterThanOrEqual`: 大于等于
- `LessThanOrEqual`: 小于等于

### 支持的动作类型

- `taint`: 添加节点污点
- `alert`: 发送告警
- `evict`: 驱逐Pod
- `label`: 添加节点标签
- `annotation`: 添加节点注解

### 支持的告警渠道

- `email`: 邮件告警
- `slack`: Slack告警
- `webhook`: Webhook告警

## 📊 监控和状态

### 查看规则状态

```bash
# 查看所有规则
kubectl get nodeguardianrules

# 查看规则详情
kubectl describe nodeguardianrule high-load-isolation

# 查看规则状态
kubectl get nodeguardianrule high-load-isolation -o yaml
```

### 查看告警模板

```bash
# 查看所有模板
kubectl get alerttemplates

# 查看模板详情
kubectl describe alerttemplate high-load-alert
```

### 查看NodeGuardian状态

```bash
# 查看Pod状态
kubectl get pods -n nodeguardian-system

# 查看日志
kubectl logs -n nodeguardian-system deployment/nodeguardian-python

# 查看服务状态
kubectl get svc -n nodeguardian-system
```

## 🔍 故障排除

### 常见问题

1. **规则不触发**
   - 检查规则是否启用 (`spec.metadata.enabled: true`)
   - 检查节点选择器是否正确
   - 检查指标数据是否可用
   - 查看NodeGuardian日志

2. **指标获取失败**
   - 检查Prometheus连接配置
   - 检查Metrics Server是否运行
   - 检查RBAC权限

3. **告警发送失败**
   - 检查告警渠道配置
   - 检查网络连接
   - 查看告警模板语法

### 调试模式

```bash
# 启用调试日志
kubectl set env deployment/nodeguardian-python LOG_LEVEL=DEBUG -n nodeguardian-system

# 查看详细日志
kubectl logs -f -n nodeguardian-system deployment/nodeguardian-python
```

## 🧪 示例

项目包含以下示例：

- `high-load-isolation.yaml`: 高负载节点隔离规则
- `disk-space-alert.yaml`: 磁盘空间告警规则
- `emergency-eviction.yaml`: 紧急驱逐规则
- `alert-templates.yaml`: 告警模板示例

## 🔄 升级和维护

### 升级NodeGuardian

```bash
# 更新镜像
docker build -t nodeguardian-python:v2.0.0 -f deploy/Dockerfile .

# 更新部署
kubectl set image deployment/nodeguardian-python nodeguardian=nodeguardian-python:v2.0.0 -n nodeguardian-system
```

### 清理部署

```bash
# 使用脚本清理
./deploy.sh --cleanup

# 或手动清理
kubectl delete -f ../examples/
kubectl delete -f deploy/
kubectl delete -f ../crd/
```

## 🤝 贡献

欢迎提交Issue和Pull Request来改进NodeGuardian Python版本。

### 开发指南

1. Fork项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 打开Pull Request

### 代码规范

- 使用Black进行代码格式化
- 使用isort进行导入排序
- 使用mypy进行类型检查
- 使用pytest进行测试
- 遵循PEP 8编码规范

## 📄 许可证

本项目采用Apache License 2.0许可证。

## 🙏 致谢

- [shell-operator](https://github.com/flant/shell-operator) - 提供事件驱动框架
- [Kubernetes](https://kubernetes.io/) - 容器编排平台
- [Prometheus](https://prometheus.io/) - 监控系统
- [Python](https://python.org/) - 编程语言
- [uv](https://github.com/astral-sh/uv) - Python包管理器
