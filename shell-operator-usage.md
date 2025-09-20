# Shell-Operator Hook 开发指南

## 目录
1. [概述](#概述)
2. [Hook基础概念](#hook基础概念)
3. [目录结构规范](#目录结构规范)
4. [函数命名约定](#函数命名约定)
5. [配置参数详解](#配置参数详解)
6. [执行顺序和频率限制](#执行顺序和频率限制)
7. [开发模板和示例](#开发模板和示例)
8. [最佳实践](#最佳实践)

## 概述

Shell-Operator是一个Kubernetes控制器，允许你通过shell脚本或任何可执行程序来响应Kubernetes事件。它通过hook机制实现事件驱动的自动化操作。

### 核心特性
- **事件驱动**: 响应Kubernetes资源变化
- **定时任务**: 支持cron格式的定时执行
- **Webhook支持**: 实现验证和变更webhook
- **多语言支持**: 支持任何可执行程序
- **队列管理**: 支持自定义队列和并发控制

## Hook基础概念

### Hook生命周期

1. **初始化阶段**
   - Shell-operator递归搜索hooks目录
   - 执行每个hook的 `--config` 参数获取配置
   - 根据配置设置事件绑定和监控

2. **运行阶段**
   - 启动时执行 `onStartup` hooks
   - 监听Kubernetes事件并触发相应hooks
   - 按计划执行定时任务hooks

### Hook通信机制

Hook通过以下方式与Shell-operator通信：

- **配置获取**: `hook --config` 返回YAML/JSON配置
- **事件处理**: 通过环境变量接收事件数据
- **结果返回**: 通过临时文件返回处理结果

## 目录结构规范

### 基本目录结构

```
/hooks/                          # 默认hooks目录
├── common/                      # 公共函数库
│   └── functions.sh            # 公共函数定义
├── 001-startup-hook.sh         # 启动hook
├── 002-monitor-pods.sh         # 监控hook
├── 003-schedule-task.sh        # 定时任务hook
├── webhook/                    # webhook相关
│   ├── validating.sh
│   └── mutating.sh
└── lib/                        # 库文件（被忽略）
```

### 命名约定

#### 文件命名
- **数字前缀**: 控制执行顺序（如 `001-`, `002-`）
- **描述性名称**: 使用连字符分隔
- **可执行权限**: 所有hook文件必须可执行

#### 目录命名
- **功能分组**: 相关功能放在子目录
- **层次清晰**: 避免过深的嵌套结构

## 函数命名约定

### 标准模式 (hook::xxx)

```bash
#!/usr/bin/env bash

source /hooks/common/functions.sh

# 配置函数 - 必须实现
hook::config() {
  cat <<EOF
{
  "configVersion": "v1",
  "onStartup": 10,
  "kubernetes": [
    {
      "apiVersion": "v1",
      "kind": "Pod"
    }
  ]
}
EOF
}

# 触发函数 - 必须实现
hook::trigger() {
  echo "Hook triggered!"
  # 处理逻辑
}

# 调用公共运行函数
common::run_hook "$@"
```

### 高级模式 (__xxx__)

```bash
#!/usr/bin/env bash

source /shell_lib.sh

# 配置函数
function __config__() {
  cat <<EOF
configVersion: v1
kubernetes:
- name: monitor-pods
  kind: Pod
EOF
}

# 特定事件处理函数
function __on_kubernetes::monitor-pods::added() {
  echo "Pod added: $(context::jq -r '.object.metadata.name')"
}

function __on_kubernetes::monitor-pods::modified() {
  echo "Pod modified: $(context::jq -r '.object.metadata.name')"
}

function __on_kubernetes::monitor-pods::deleted() {
  echo "Pod deleted: $(context::jq -r '.object.metadata.name')"
}

# 启动处理函数
function __on_startup() {
  echo "Startup hook executed"
}

# 定时任务处理函数
function __on_schedule::daily-cleanup() {
  echo "Daily cleanup executed"
}

# 主函数（兜底处理）
function __main__() {
  echo "Default handler"
}

# 调用框架运行函数
hook::run "$@"
```

## 配置参数详解

### 基础配置结构

```yaml
configVersion: v1  # 配置版本，当前支持v1

# 启动配置
onStartup: 10

# 定时任务配置
schedule:
- name: "daily-cleanup"
  crontab: "0 2 * * *"
  allowFailure: true
  queue: "cleanup-queue"

# Kubernetes事件配置
kubernetes:
- name: "monitor-pods"
  apiVersion: "v1"
  kind: "Pod"
  executeHookOnEvent: ["Added", "Modified", "Deleted"]
  namespace:
    nameSelector:
      matchNames: ["default"]

# 频率限制配置
settings:
  executionMinInterval: 3s
  executionBurst: 1
```

### 配置类型详解

#### onStartup配置
```yaml
onStartup: 10  # 数字越小，执行越早
```

#### schedule配置
```yaml
schedule:
- name: "task-name"           # 任务名称
  crontab: "*/5 * * * *"      # cron表达式
  allowFailure: true          # 允许失败
  queue: "custom-queue"       # 自定义队列
  group: "monitoring"         # 分组名称
  includeSnapshotsFrom:       # 包含快照
  - "monitor-pods"
```

#### kubernetes配置
```yaml
kubernetes:
- name: "monitor-pods"                    # 绑定名称
  apiVersion: "v1"                        # API版本
  kind: "Pod"                             # 资源类型
  executeHookOnEvent: ["Added", "Modified", "Deleted"]  # 监听事件
  executeHookOnSynchronization: true      # 启动时同步
  nameSelector:                           # 名称选择器
    matchNames: ["pod-1", "pod-2"]
  labelSelector:                          # 标签选择器
    matchLabels:
      app: "nginx"
    matchExpressions:
    - key: "tier"
      operator: "In"
      values: ["cache"]
  fieldSelector:                          # 字段选择器
    matchExpressions:
    - field: "status.phase"
      operator: "Equals"
      value: "Running"
  namespace:                              # 命名空间选择器
    nameSelector:
      matchNames: ["default", "kube-system"]
    labelSelector:
      matchLabels:
        env: "production"
  jqFilter: ".metadata.labels"            # jq过滤器
  allowFailure: false                     # 错误处理
  queue: "pods-queue"                     # 自定义队列
  group: "monitoring"                     # 分组
  includeSnapshotsFrom:                   # 包含快照
  - "monitor-services"
  keepFullObjectsInMemory: true           # 保持完整对象
```

## 执行顺序和频率限制

### 执行顺序配置

#### 1. onStartup执行顺序
```yaml
onStartup: 5   # 数字越小，执行越早
```
- 按数值从小到大排序
- 相同数值按文件名字母顺序排序

#### 2. 文件路径排序
所有hook按文件路径字母顺序排序：
```bash
001-startup-shell/hook.sh    # 先执行
002-startup-python/hook.py   # 后执行
```

### 队列配置

#### 默认队列
```yaml
kubernetes:
- name: "monitor-pods"
  kind: Pod
  # 默认使用 "main" 队列
```

#### 自定义队列
```yaml
kubernetes:
- name: "monitor-pods"
  kind: Pod
  queue: "pods-queue"  # 使用自定义队列
```

**队列特性**:
- 每个队列内的hook**严格串行执行**
- 不同队列可以**并行执行**
- 队列内hook失败会阻塞该队列

### 分组配置

```yaml
kubernetes:
- name: "monitor-pods"
  kind: Pod
  group: "monitoring"  # 分组名称

- name: "monitor-services"
  kind: Service
  group: "monitoring"  # 同一分组
```

**分组特性**:
- 同组内的多个事件会被**合并**为一次执行
- 减少重复执行，提高效率

### 频率限制配置

```yaml
settings:
  executionMinInterval: 3s  # 最小执行间隔
  executionBurst: 1         # 突发执行数量
```

**Token Bucket算法**:
- `executionMinInterval`: 定义两次执行之间的最小时间间隔
- `executionBurst`: 定义在时间窗口内允许的最大执行次数

### 错误处理配置

```yaml
kubernetes:
- name: "monitor-pods"
  kind: Pod
  allowFailure: true  # 允许失败，不重试
```

**行为差异**:
- `allowFailure: true`: hook失败时跳过，不重试
- `allowFailure: false` (默认): hook失败时每5秒重试一次

## 开发模板和示例

### 公共函数库模板

```bash
#!/usr/bin/env bash
# 文件: /hooks/common/functions.sh

# 标准hook运行函数
common::run_hook() {
  if [[ $1 == "--config" ]] ; then
    hook::config
  else
    hook::trigger
  fi
}

# 工具函数
kubectl::replace_or_create() {
  object=$(cat)
  
  if ! kubectl get -f - <<< "$object" >/dev/null 2>/dev/null; then
    kubectl create -f - <<< "$object" >/dev/null
  else
    kubectl replace --force -f - <<< "$object" >/dev/null
  fi
}

# 日志函数
log::info() {
  echo "[INFO] $*"
}

log::error() {
  echo "[ERROR] $*" >&2
}

# 验证函数
validate::required() {
  local var_name="$1"
  local var_value="${!var_name:-}"
  
  if [[ -z "$var_value" ]]; then
    log::error "Required variable $var_name is not set"
    exit 1
  fi
}
```

### 示例1: 简单启动Hook

```bash
#!/usr/bin/env bash
# 文件: /hooks/001-startup.sh

source /hooks/common/functions.sh

hook::config() {
  echo '{"configVersion": "v1", "onStartup": 10}'
}

hook::trigger() {
  echo "Startup hook executed at $(date)"
  # 初始化逻辑
}

common::run_hook "$@"
```

### 示例2: Kubernetes事件监控Hook

```bash
#!/usr/bin/env bash
# 文件: /hooks/002-monitor-pods.sh

source /hooks/common/functions.sh

hook::config() {
  cat <<EOF
{
  "configVersion": "v1",
  "kubernetes": [
    {
      "name": "monitor-pods",
      "apiVersion": "v1",
      "kind": "Pod",
      "executeHookOnEvent": ["Added", "Modified", "Deleted"],
      "namespace": {
        "nameSelector": {
          "matchNames": ["default"]
        }
      }
    }
  ]
}
EOF
}

hook::trigger() {
  local type=$(jq -r '.[0].type' $BINDING_CONTEXT_PATH)
  
  if [[ $type == "Synchronization" ]]; then
    echo "Got synchronization event"
    return 0
  fi
  
  local event=$(jq -r '.[0].watchEvent' $BINDING_CONTEXT_PATH)
  local pod_name=$(jq -r '.[0].object.metadata.name' $BINDING_CONTEXT_PATH)
  
  case $event in
    "Added")
      echo "Pod $pod_name was added"
      ;;
    "Modified")
      echo "Pod $pod_name was modified"
      ;;
    "Deleted")
      echo "Pod $pod_name was deleted"
      ;;
  esac
}

common::run_hook "$@"
```

### 示例3: 定时任务Hook

```bash
#!/usr/bin/env bash
# 文件: /hooks/003-schedule-cleanup.sh

source /hooks/common/functions.sh

hook::config() {
  cat <<EOF
{
  "configVersion": "v1",
  "schedule": [
    {
      "name": "daily-cleanup",
      "crontab": "0 2 * * *",
      "allowFailure": true
    },
    {
      "name": "hourly-check",
      "crontab": "0 * * * *"
    }
  ]
}
EOF
}

hook::trigger() {
  local binding=$(jq -r '.[0].binding' $BINDING_CONTEXT_PATH)
  
  case $binding in
    "daily-cleanup")
      echo "Running daily cleanup at $(date)"
      # 清理逻辑
      ;;
    "hourly-check")
      echo "Running hourly check at $(date)"
      # 检查逻辑
      ;;
  esac
}

common::run_hook "$@"
```

### 示例4: 高级事件处理Hook

```bash
#!/usr/bin/env bash
# 文件: /hooks/004-advanced-monitor.sh

source /shell_lib.sh

function __config__() {
  cat <<EOF
configVersion: v1
kubernetes:
- name: monitor-secrets
  apiVersion: v1
  kind: Secret
  executeHookOnEvent: ["Added", "Modified"]
  labelSelector:
    matchLabels:
      secret-copier: "yes"
- name: monitor-namespaces
  apiVersion: v1
  kind: Namespace
  executeHookOnEvent: ["Added"]
schedule:
- name: sync-secrets
  crontab: "*/5 * * * *"
  group: "secrets"
EOF
}

function __on_kubernetes::monitor-secrets::added() {
  local secret_name=$(context::jq -r '.object.metadata.name')
  echo "Secret $secret_name was added"
  # 复制secret到其他namespace
}

function __on_kubernetes::monitor-secrets::modified() {
  local secret_name=$(context::jq -r '.object.metadata.name')
  echo "Secret $secret_name was modified"
  # 更新其他namespace中的secret
}

function __on_kubernetes::monitor-namespaces::added() {
  local namespace=$(context::jq -r '.object.metadata.name')
  echo "Namespace $namespace was created"
  # 在新namespace中创建必要的资源
}

function __on_schedule::sync-secrets() {
  echo "Synchronizing secrets at $(date)"
  # 同步所有secrets
}

function __main__() {
  echo "Default handler for unhandled events"
}

hook::run "$@"
```

### 示例5: 验证Webhook

```bash
#!/usr/bin/env bash
# 文件: /hooks/005-validating-webhook.sh

source /shell_lib.sh

function __config__() {
  cat <<EOF
configVersion: v1
kubernetesValidating:
- name: validate-images
  namespace:
    labelSelector:
      matchLabels:
        name: example-namespace
  rules:
  - apiGroups: ["apps"]
    apiVersions: ["v1"]
    operations: ["CREATE", "UPDATE"]
    resources: ["deployments"]
    scope: "Namespaced"
EOF
}

function __on_validating::validate-images() {
  local image=$(context::jq -r '.review.request.object.spec.template.spec.containers[0].image')
  echo "Validating image: $image"
  
  if [[ $image == repo.example.com* ]]; then
    cat <<EOF > $VALIDATING_RESPONSE_PATH
{"allowed": true}
EOF
  else
    cat <<EOF > $VALIDATING_RESPONSE_PATH
{"allowed": false, "message": "Only images from repo.example.com are allowed"}
EOF
  fi
}

hook::run "$@"
```

### 示例6: 变更Webhook

```bash
#!/usr/bin/env bash
# 文件: /hooks/006-mutating-webhook.sh

source /shell_lib.sh

function __config__() {
  cat <<EOF
configVersion: v1
kubernetesMutating:
- name: add-labels
  namespace:
    labelSelector:
      matchLabels:
        name: example-namespace
  rules:
  - apiGroups: ["apps"]
    apiVersions: ["v1"]
    operations: ["CREATE", "UPDATE"]
    resources: ["deployments"]
    scope: "Namespaced"
EOF
}

function __on_mutating::add-labels() {
  local patch='[{"op": "add", "path": "/metadata/labels/managed-by", "value": "shell-operator"}]'
  local patch_base64=$(echo "$patch" | base64 -w 0)
  
  cat <<EOF > $ADMISSION_RESPONSE_PATH
{"allowed": true, "patch": "$patch_base64"}
EOF
}

hook::run "$@"
```

## 最佳实践

### 1. 目录和文件组织
- 使用数字前缀控制执行顺序
- 将公共函数放在 `common/` 目录
- 保持文件名描述性和一致性

### 2. 函数命名
- 使用 `hook::` 前缀或 `__xxx__` 模式
- 保持命名约定的一致性
- 为函数添加清晰的注释

### 3. 错误处理
- 在公共函数中添加错误处理逻辑
- 使用 `allowFailure` 控制重试行为
- 记录详细的错误日志

### 4. 性能优化
- 使用分组减少重复执行
- 合理设置频率限制
- 为长时间运行的hook使用独立队列

### 5. 安全考虑
- 验证输入参数
- 使用RBAC控制权限
- 避免在hook中存储敏感信息

### 6. 监控和调试
- 添加详细的日志记录
- 使用metrics收集性能数据
- 提供清晰的错误信息

### 7. 测试
- 为hook编写单元测试
- 使用模拟数据进行测试
- 验证配置的正确性

### 8. 文档
- 为每个hook编写清晰的文档
- 说明hook的用途和配置
- 提供使用示例

---

这个开发指南涵盖了Shell-Operator Hook开发的所有重要方面，从基础概念到高级用法，从配置参数到最佳实践。遵循这些规范和约定，可以开发出高质量、可维护的Hook程序。

-------

让我查看shell-operator中关于`executeHookOnSynchronization`的具体含义和用法。


[1 tool called]

让我查看一些具体的示例来更好地理解这个参数：


[1 tool called]

让我查看nodeguardian项目中的实际使用情况：


[1 tool called]

现在让我查看文档中关于Synchronization的详细说明：


[1 tool called]

基于我对代码和文档的分析，现在我可以详细解释`executeHookOnSynchronization`参数的含义：

## `executeHookOnSynchronization` 参数详解

### 基本含义

`executeHookOnSynchronization` 是一个布尔值参数，用于控制hook是否在**启动同步阶段**执行。

### 工作原理

#### 1. **Synchronization阶段**
当shell-operator启动时，会经历以下阶段：

1. **初始化阶段**: 加载所有hook配置
2. **同步阶段**: 为每个kubernetes绑定获取当前集群中所有匹配的资源
3. **监听阶段**: 开始监听Kubernetes事件变化

#### 2. **参数控制**
```yaml
kubernetes:
- name: "monitor-pods"
  kind: Pod
  executeHookOnSynchronization: true   # 默认值
  executeHookOnEvent: ["Added", "Modified", "Deleted"]
```

- `executeHookOnSynchronization: true` (默认): 在同步阶段执行hook
- `executeHookOnSynchronization: false`: 跳过同步阶段，只监听后续事件

### 实际应用场景

#### 场景1: 需要处理现有资源
```yaml
kubernetes:
- name: "monitor-pods"
  kind: Pod
  executeHookOnSynchronization: true  # 处理启动时已存在的Pod
  executeHookOnEvent: ["Added", "Modified", "Deleted"]
```

**用途**: 当你需要处理集群中已经存在的资源时使用。例如：
- 初始化配置
- 同步状态
- 建立索引

#### 场景2: 只处理新事件
```yaml
kubernetes:
- name: "monitor-pods"
  kind: Pod
  executeHookOnSynchronization: false  # 不处理现有Pod
  executeHookOnEvent: ["Added", "Modified", "Deleted"]
```

**用途**: 当你只关心资源变化，不关心现有资源时使用。例如：
- 实时监控
- 事件响应
- 避免重复处理

#### 场景3: 快照专用绑定
```yaml
kubernetes:
- name: "configmap-snapshot"
  kind: ConfigMap
  nameSelector:
    matchNames: ["app-config"]
  executeHookOnSynchronization: false
  executeHookOnEvent: []  # 空数组，不处理任何事件
```

**用途**: 创建一个"快照专用"绑定，只用于在`includeSnapshotsFrom`中引用，不执行hook。

### 代码中的处理逻辑

从shell-operator源码可以看到：

```go
isSynchronization := hookMeta.IsSynchronization()
shouldRunHook := true
if isSynchronization {
    // 显式设置 "executeOnSynchronization: false"
    if !hookMeta.ExecuteOnSynchronization {
        shouldRunHook = false
    }
}
```

### 实际示例

#### 示例1: 处理现有资源
```bash
#!/usr/bin/env bash

hook::config() {
  cat <<EOF
{
  "configVersion": "v1",
  "kubernetes": [
    {
      "name": "monitor-pods",
      "kind": "Pod",
      "executeHookOnSynchronization": true,
      "executeHookOnEvent": ["Added", "Modified", "Deleted"]
    }
  ]
}
EOF
}

hook::trigger() {
  local context_type=$(jq -r '.[0].type' $BINDING_CONTEXT_PATH)
  
  case "$context_type" in
    "Synchronization")
      echo "处理启动时已存在的Pod"
      # 处理所有现有Pod
      jq -r '.[0].objects[].object.metadata.name' $BINDING_CONTEXT_PATH | while read pod_name; do
        echo "初始化Pod: $pod_name"
      done
      ;;
    "Event")
      local event=$(jq -r '.[0].watchEvent' $BINDING_CONTEXT_PATH)
      local pod_name=$(jq -r '.[0].object.metadata.name' $BINDING_CONTEXT_PATH)
      echo "Pod $pod_name 发生了 $event 事件"
      ;;
  esac
}
```

#### 示例2: 只处理新事件
```bash
#!/usr/bin/env bash

hook::config() {
  cat <<EOF
{
  "configVersion": "v1",
  "kubernetes": [
    {
      "name": "monitor-pods",
      "kind": "Pod",
      "executeHookOnSynchronization": false,
      "executeHookOnEvent": ["Added", "Modified", "Deleted"]
    }
  ]
}
EOF
}

hook::trigger() {
  local context_type=$(jq -r '.[0].type' $BINDING_CONTEXT_PATH)
  
  if [[ "$context_type" == "Synchronization" ]]; then
    echo "跳过同步阶段，不处理现有Pod"
    return 0
  fi
  
  # 只处理新事件
  local event=$(jq -r '.[0].watchEvent' $BINDING_CONTEXT_PATH)
  local pod_name=$(jq -r '.[0].object.metadata.name' $BINDING_CONTEXT_PATH)
  echo "处理Pod $pod_name 的 $event 事件"
}
```

#### 示例3: 快照专用绑定
```yaml
configVersion: v1
kubernetes:
- name: "configmap-snapshot"
  kind: ConfigMap
  nameSelector:
    matchNames: ["app-config"]
  executeHookOnSynchronization: false
  executeHookOnEvent: []  # 不处理任何事件
- name: "monitor-pods"
  kind: Pod
  includeSnapshotsFrom: ["configmap-snapshot"]  # 引用快照
```

### 最佳实践

1. **默认使用true**: 除非有特殊需求，否则保持默认值`true`
2. **性能考虑**: 如果资源很多且不需要处理现有资源，可以设置为`false`
3. **快照绑定**: 用于`includeSnapshotsFrom`的绑定通常设置为`false`
4. **明确意图**: 在配置中明确说明为什么设置这个值

### 总结

`executeHookOnSynchronization` 参数控制hook是否在shell-operator启动时处理集群中已存在的资源。这是一个重要的性能和行为控制参数，合理使用可以避免不必要的处理，提高hook的执行效率。