# NodeGuardian Shell Version

NodeGuardian是一个基于shell-operator的事件驱动Kubernetes节点自愈工具，采用标准的shell-operator hook目录规范和函数命名约定。

## 项目结构

```
nodeguardian/
├── hooks/                          # Shell-operator hooks目录
│   ├── common/                     # 公共函数库
│   │   └── functions.sh           # 标准hook运行函数和工具函数
│   ├── 001-nodeguardian-controller.sh  # 主控制器hook
│   ├── 002-alert-manager.sh       # 告警管理器hook
│   └── 003-recovery-manager.sh    # 恢复管理器hook
├── crd/                           # 自定义资源定义
│   ├── nodeguardianrule-crd.yaml  # NodeGuardianRule CRD
│   └── alerttemplate-crd.yaml     # AlertTemplate CRD
├── deploy/                        # 部署配置
│   ├── Dockerfile                 # Docker镜像构建文件
│   ├── namespace.yaml             # 命名空间配置
│   ├── rbac.yaml                  # RBAC权限配置
│   └── deployment.yaml            # 部署配置
├── examples/                      # 示例配置
│   ├── high-load-isolation.yaml   # 高负载隔离示例
│   ├── disk-space-alert.yaml      # 磁盘空间告警示例
│   ├── emergency-eviction.yaml    # 紧急驱逐示例
│   └── alert-templates.yaml       # 告警模板示例
├── deploy.sh                      # 部署脚本
└── README.md                      # 项目说明
```

## 核心特性

### 1. 标准Shell-Operator Hook结构

- **数字前缀命名**: 使用`001-`, `002-`, `003-`等前缀控制执行顺序
- **标准函数命名**: 使用`hook::config()`和`hook::trigger()`函数
- **公共函数库**: 统一的工具函数和错误处理
- **模块化设计**: 每个hook负责特定功能

### 2. 事件驱动架构

- **Kubernetes事件监听**: 监听NodeGuardianRule和AlertTemplate CRD变化
- **定时任务调度**: 定期评估规则条件和恢复条件
- **绑定上下文处理**: 标准化的shell-operator绑定上下文处理

### 3. 规则引擎

- **条件评估**: 支持CPU、内存、磁盘、负载等指标监控
- **逻辑操作符**: 支持AND/OR逻辑组合
- **冷却期管理**: 防止规则频繁触发
- **节点选择器**: 灵活的节点选择机制

### 4. 动作执行

- **污点管理**: 自动添加/移除节点污点
- **标签注解**: 动态管理节点标签和注解
- **Pod驱逐**: 智能驱逐节点上的Pod
- **告警通知**: 多渠道告警通知

### 5. 恢复机制

- **恢复条件**: 独立的恢复条件评估
- **自动恢复**: 条件满足时自动执行恢复动作
- **状态管理**: 完整的规则状态跟踪

## 快速开始

### 1. 构建和部署

```bash
# 构建Docker镜像
./deploy.sh build

# 部署到Kubernetes
./deploy.sh deploy

# 查看部署状态
./deploy.sh status
```

### 2. 创建示例规则

```bash
# 部署示例规则
kubectl apply -f examples/high-load-isolation.yaml
kubectl apply -f examples/disk-space-alert.yaml
kubectl apply -f examples/emergency-eviction.yaml

# 部署告警模板
kubectl apply -f examples/alert-templates.yaml
```

### 3. 监控和日志

```bash
# 查看日志
./deploy.sh logs

# 查看规则状态
kubectl get nodeguardianrules
kubectl describe nodeguardianrule high-load-isolation

# 查看告警模板
kubectl get alerttemplates
```

## Hook详细说明

### 001-nodeguardian-controller.sh

主控制器hook，负责：
- 监听NodeGuardianRule和AlertTemplate CRD事件
- 管理规则生命周期（注册/注销）
- 定期评估规则条件
- 执行规则动作

**配置绑定**:
- `monitor-nodeguardian-rules`: 监听NodeGuardianRule CRD
- `monitor-alert-templates`: 监听AlertTemplate CRD
- `rule-evaluation`: 每分钟执行规则评估

### 002-alert-manager.sh

告警管理器hook，负责：
- 管理告警模板
- 渲染告警内容
- 发送多渠道告警

**支持的告警渠道**:
- 日志输出
- Webhook
- 邮件
- Slack
- Microsoft Teams

### 003-recovery-manager.sh

恢复管理器hook，负责：
- 定期检查恢复条件
- 执行恢复动作
- 管理恢复状态

**恢复动作**:
- 移除污点
- 移除标签
- 移除注解
- 发送恢复告警

## 公共函数库

`hooks/common/functions.sh`提供以下功能：

### 标准Hook运行函数
- `common::run_hook()`: 标准hook运行入口

### 日志函数
- `log::info()`, `log::warn()`, `log::error()`, `log::debug()`

### 验证函数
- `validate::required()`, `validate::file_exists()`

### Kubernetes工具函数
- `kubectl::replace_or_create()`, `kubectl::apply()`, `kubectl::delete()`

### 指标收集函数
- `metrics::get_node_cpu_utilization()`
- `metrics::get_node_memory_utilization()`
- `metrics::get_node_disk_utilization()`
- `metrics::get_node_cpu_load_ratio()`

### 条件评估函数
- `condition::evaluate()`: 评估条件是否满足

### 冷却期管理函数
- `cooldown::check()`, `cooldown::set()`

### 节点选择器函数
- `node::get_matching()`: 获取匹配的节点列表

## 配置说明

### 环境变量

- `LOG_LEVEL`: 日志级别 (DEBUG, INFO, WARN, ERROR)
- `NODEGUARDIAN_NAMESPACE`: 命名空间 (默认: nodeguardian-system)
- `PROMETHEUS_URL`: Prometheus服务地址
- `METRICS_SERVER_URL`: Metrics Server地址

### 规则配置

NodeGuardianRule支持以下配置：

```yaml
apiVersion: nodeguardian.k8s.io/v1
kind: NodeGuardianRule
metadata:
  name: example-rule
spec:
  metadata:
    enabled: true
    description: "Example rule"
    severity: "warning"
  nodeSelector:
    matchLabels:
      node-role.kubernetes.io/worker: ""
  conditions:
  - metric: "cpuUtilizationPercent"
    operator: "GreaterThan"
    value: 80
    duration: "5m"
  conditionLogic: "AND"
  actions:
  - type: "taint"
    taint:
      key: "nodeguardian/high-cpu"
      value: "true"
      effect: "NoSchedule"
  - type: "alert"
    alert:
      enabled: true
      template: "high-cpu-alert"
  recoveryConditions:
  - metric: "cpuUtilizationPercent"
    operator: "LessThan"
    value: 60
    duration: "2m"
  recoveryActions:
  - type: "untaint"
    untaint:
      key: "nodeguardian/high-cpu"
  monitoring:
    checkInterval: "60s"
    cooldownPeriod: "5m"
    recoveryCooldownPeriod: "2m"
```

## 最佳实践

### 1. 规则设计

- 合理设置冷却期，避免频繁触发
- 使用适当的严重程度级别
- 配置恢复条件，确保自动恢复
- 测试规则在非生产环境

### 2. 告警配置

- 配置多个告警渠道
- 设置合适的告警模板
- 避免告警风暴
- 定期测试告警功能

### 3. 监控和运维

- 监控NodeGuardian自身状态
- 定期检查规则执行情况
- 收集和分析告警数据
- 及时更新规则配置

## 故障排除

### 常见问题

1. **Hook不执行**
   - 检查hook文件权限
   - 查看shell-operator日志
   - 验证绑定上下文

2. **规则不触发**
   - 检查节点选择器
   - 验证指标数据源
   - 查看冷却期设置

3. **告警不发送**
   - 检查告警模板配置
   - 验证告警渠道设置
   - 查看网络连接

### 调试方法

```bash
# 查看详细日志
kubectl logs -f deployment/nodeguardian-controller -n nodeguardian-system

# 检查hook配置
kubectl exec -it deployment/nodeguardian-controller -n nodeguardian-system -- /hooks/001-nodeguardian-controller.sh --config

# 查看规则状态
kubectl get nodeguardianrules -o yaml
```

## 贡献指南

1. Fork项目
2. 创建功能分支
3. 遵循shell-operator标准
4. 添加测试用例
5. 提交Pull Request

## 许可证

Apache License 2.0

## 支持

如有问题，请提交Issue或联系维护团队。