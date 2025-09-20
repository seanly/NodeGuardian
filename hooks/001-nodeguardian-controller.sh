#!/usr/bin/env bash

# NodeGuardian Main Controller Hook
# 监听NodeGuardianRule CRD变化并管理规则生命周期

set -euo pipefail

# 加载公共函数库
source /hooks/common/functions.sh

# Hook配置函数
hook::config() {
    cat <<EOF
{
  "configVersion": "v1",
  "onStartup": 1,
  "kubernetes": [
    {
      "name": "monitor-nodeguardian-rules",
      "apiVersion": "nodeguardian.k8s.io/v1",
      "kind": "NodeGuardianRule",
      "executeHookOnEvent": ["Added", "Modified", "Deleted"],
      "executeHookOnSynchronization": true,
      "queue": "nodeguardian-rules"
    },
    {
      "name": "monitor-alert-templates",
      "apiVersion": "nodeguardian.k8s.io/v1",
      "kind": "AlertTemplate",
      "executeHookOnEvent": ["Added", "Modified", "Deleted"],
      "executeHookOnSynchronization": true,
      "queue": "nodeguardian-rules"
    }
  ],
  "schedule": [
    {
      "name": "rule-evaluation",
      "crontab": "*/1 * * * *",
      "queue": "rule-evaluation",
      "includeSnapshotsFrom": ["monitor-nodeguardian-rules"]
    }
  ],
  "settings": {
    "executionMinInterval": "10s",
    "executionBurst": 1
  }
}
EOF
}

# Hook触发函数
hook::trigger() {
    # 初始化
    init::nodeguardian
    
    # 读取绑定上下文
    local binding_context_path="${BINDING_CONTEXT_PATH:-/tmp/binding_context.json}"
    validate::file_exists "$binding_context_path"
    
    # 处理绑定上下文
    local context_type=$(jq -r '.[0].type' "$binding_context_path")
    local binding=$(jq -r '.[0].binding' "$binding_context_path")
    
    log::info "Processing binding context: type=$context_type, binding=$binding"
    
    case "$context_type" in
        "onStartup")
            hook::handle_startup
            ;;
        "Synchronization")
            hook::handle_synchronization "$binding"
            ;;
        "Event")
            hook::handle_event "$binding" "$binding_context_path"
            ;;
        "Schedule")
            hook::handle_schedule "$binding"
            ;;
        *)
            log::warn "Unknown binding context type: $context_type"
            ;;
    esac
}

# 处理启动事件
hook::handle_startup() {
    log::info "NodeGuardian controller starting up..."
    
    # 创建必要的资源
    hook::create_namespace_if_not_exists
    hook::create_configmap_if_not_exists
    
    # 初始化所有现有规则
    hook::initialize_existing_rules
    
    log::info "NodeGuardian controller startup completed"
}

# 处理同步事件
hook::handle_synchronization() {
    local binding="$1"
    
    case "$binding" in
        "monitor-nodeguardian-rules")
            hook::handle_rules_synchronization
            ;;
        "monitor-alert-templates")
            hook::handle_templates_synchronization
            ;;
    esac
}

# 处理规则同步
hook::handle_rules_synchronization() {
    local binding_context_path="${BINDING_CONTEXT_PATH:-/tmp/binding_context.json}"
    local rules_count=$(jq -r '.[0].objects | length' "$binding_context_path")
    log::info "Synchronizing $rules_count NodeGuardianRule objects"
    
    for ((i=0; i<rules_count; i++)); do
        local rule_object=$(jq -r ".[0].objects[$i].object" "$binding_context_path")
        local rule_name=$(echo "$rule_object" | jq -r '.metadata.name')
        local rule_enabled=$(echo "$rule_object" | jq -r '.spec.metadata.enabled // true')
        
        if [[ "$rule_enabled" == "true" ]]; then
            hook::register_rule "$rule_object"
        else
            hook::unregister_rule "$rule_name"
        fi
    done
}

# 处理模板同步
hook::handle_templates_synchronization() {
    local binding_context_path="${BINDING_CONTEXT_PATH:-/tmp/binding_context.json}"
    local templates_count=$(jq -r '.[0].objects | length' "$binding_context_path")
    log::info "Synchronizing $templates_count AlertTemplate objects"
    
    for ((i=0; i<templates_count; i++)); do
        local template_object=$(jq -r ".[0].objects[$i].object" "$binding_context_path")
        local template_name=$(echo "$template_object" | jq -r '.metadata.name')
        
        hook::register_alert_template "$template_object"
    done
}

# 处理事件
hook::handle_event() {
    local binding="$1"
    local binding_context_path="$2"
    local watch_event=$(jq -r '.[0].watchEvent' "$binding_context_path")
    local object=$(jq -r '.[0].object' "$binding_context_path")
    
    case "$binding" in
        "monitor-nodeguardian-rules")
            hook::handle_rule_event "$watch_event" "$object"
            ;;
        "monitor-alert-templates")
            hook::handle_template_event "$watch_event" "$object"
            ;;
    esac
}

# 处理规则事件
hook::handle_rule_event() {
    local watch_event="$1"
    local rule_object="$2"
    local rule_name=$(echo "$rule_object" | jq -r '.metadata.name')
    
    log::info "Processing rule event: $watch_event for rule: $rule_name"
    
    case "$watch_event" in
        "Added"|"Modified")
            local rule_enabled=$(echo "$rule_object" | jq -r '.spec.metadata.enabled // true')
            if [[ "$rule_enabled" == "true" ]]; then
                hook::register_rule "$rule_object"
            else
                hook::unregister_rule "$rule_name"
            fi
            ;;
        "Deleted")
            hook::unregister_rule "$rule_name"
            ;;
    esac
}

# 处理模板事件
hook::handle_template_event() {
    local watch_event="$1"
    local template_object="$2"
    local template_name=$(echo "$template_object" | jq -r '.metadata.name')
    
    log::info "Processing template event: $watch_event for template: $template_name"
    
    case "$watch_event" in
        "Added"|"Modified")
            hook::register_alert_template "$template_object"
            ;;
        "Deleted")
            hook::unregister_alert_template "$template_name"
            ;;
    esac
}

# 处理定时任务
hook::handle_schedule() {
    local binding="$1"
    
    if [[ "$binding" == "rule-evaluation" ]]; then
        hook::evaluate_all_rules
    fi
}

# 注册规则
hook::register_rule() {
    local rule_object="$1"
    local rule_name=$(echo "$rule_object" | jq -r '.metadata.name')
    local check_interval=$(echo "$rule_object" | jq -r '.spec.monitoring.checkInterval // "60s"')
    
    log::info "Registering rule: $rule_name with check interval: $check_interval"
    
    # 保存规则到文件
    local rule_file="/tmp/nodeguardian/rules/${rule_name}.json"
    mkdir -p "$(dirname "$rule_file")"
    echo "$rule_object" > "$rule_file"
    
    # 更新状态
    rule::update_status "$rule_name" "Active" "" "[]"
    
    log::info "Rule registered: $rule_name"
}

# 注销规则
hook::unregister_rule() {
    local rule_name="$1"
    
    log::info "Unregistering rule: $rule_name"
    
    # 删除规则文件
    local rule_file="/tmp/nodeguardian/rules/${rule_name}.json"
    rm -f "$rule_file"
    
    # 清理冷却期文件
    rm -f "/tmp/nodeguardian/cooldown/${rule_name}_"*
    
    # 更新状态
    rule::update_status "$rule_name" "Inactive" "Rule deleted" "[]"
    
    log::info "Rule unregistered: $rule_name"
}

# 注册告警模板
hook::register_alert_template() {
    local template_object="$1"
    local template_name=$(echo "$template_object" | jq -r '.metadata.name')
    
    log::info "Registering alert template: $template_name"
    
    # 保存模板到文件
    local template_file="/tmp/nodeguardian/templates/${template_name}.json"
    mkdir -p "$(dirname "$template_file")"
    echo "$template_object" > "$template_file"
    
    log::info "Alert template registered: $template_name"
}

# 注销告警模板
hook::unregister_alert_template() {
    local template_name="$1"
    
    log::info "Unregistering alert template: $template_name"
    
    # 删除模板文件
    local template_file="/tmp/nodeguardian/templates/${template_name}.json"
    rm -f "$template_file"
    
    log::info "Alert template unregistered: $template_name"
}

# 评估所有规则
hook::evaluate_all_rules() {
    local rules_dir="/tmp/nodeguardian/rules"
    
    if [[ ! -d "$rules_dir" ]]; then
        return 0
    fi
    
    log::debug "Evaluating all active rules..."
    
    for rule_file in "$rules_dir"/*.json; do
        if [[ -f "$rule_file" ]]; then
            local rule_name=$(basename "$rule_file" .json)
            hook::evaluate_rule "$rule_file"
        fi
    done
}

# 评估单个规则
hook::evaluate_rule() {
    local rule_file="$1"
    local rule_object=$(cat "$rule_file")
    local rule_name=$(echo "$rule_object" | jq -r '.metadata.name')
    local rule_enabled=$(echo "$rule_object" | jq -r '.spec.metadata.enabled // true')
    
    if [[ "$rule_enabled" != "true" ]]; then
        return 0
    fi
    
    log::debug "Evaluating rule: $rule_name"
    
    # 获取节点选择器
    local node_selector=$(echo "$rule_object" | jq -r '.spec.nodeSelector')
    local matching_nodes=$(node::get_matching "$node_selector")
    
    if [[ -z "$matching_nodes" ]]; then
        log::warn "No matching nodes found for rule: $rule_name"
        return 0
    fi
    
    # 评估每个节点
    local triggered_nodes=()
    for node_name in $matching_nodes; do
        if hook::evaluate_node_for_rule "$rule_object" "$node_name"; then
            triggered_nodes+=("$node_name")
        fi
    done
    
    # 如果有节点触发，执行动作
    if [[ ${#triggered_nodes[@]} -gt 0 ]]; then
        local triggered_nodes_json=$(printf '%s\n' "${triggered_nodes[@]}" | jq -R . | jq -s .)
        hook::execute_rule_actions "$rule_object" "$triggered_nodes_json"
        rule::update_status "$rule_name" "Active" "Rule triggered" "$triggered_nodes_json"
    fi
}

# 评估节点是否满足规则条件
hook::evaluate_node_for_rule() {
    local rule_object="$1"
    local node_name="$2"
    local rule_name=$(echo "$rule_object" | jq -r '.metadata.name')
    
    # 检查冷却期
    local cooldown_period=$(echo "$rule_object" | jq -r '.spec.monitoring.cooldownPeriod // "5m"')
    if cooldown::check "$rule_name" "$node_name" "$cooldown_period"; then
        log::debug "Rule $rule_name for node $node_name is in cooldown period"
        return 1
    fi
    
    # 获取条件
    local conditions=$(echo "$rule_object" | jq -r '.spec.conditions')
    local condition_logic=$(echo "$rule_object" | jq -r '.spec.conditionLogic // "AND"')
    
    local condition_count=$(echo "$conditions" | jq 'length')
    local satisfied_conditions=0
    
    # 评估每个条件
    for ((i=0; i<condition_count; i++)); do
        local condition=$(echo "$conditions" | jq -r ".[$i]")
        local metric=$(echo "$condition" | jq -r '.metric')
        local operator=$(echo "$condition" | jq -r '.operator')
        local threshold=$(echo "$condition" | jq -r '.value')
        local duration=$(echo "$condition" | jq -r '.duration // "5m"')
        
        # 获取指标值
        local metric_value
        case "$metric" in
            "cpuUtilizationPercent")
                metric_value=$(metrics::get_node_cpu_utilization "$node_name")
                ;;
            "memoryUtilizationPercent")
                metric_value=$(metrics::get_node_memory_utilization "$node_name")
                ;;
            "diskUtilizationPercent")
                metric_value=$(metrics::get_node_disk_utilization "$node_name")
                ;;
            "cpuLoadRatio")
                metric_value=$(metrics::get_node_cpu_load_ratio "$node_name")
                ;;
            *)
                log::error "Unknown metric type: $metric"
                return 1
                ;;
        esac
        
        # 评估条件
        if condition::evaluate "$metric_value" "$operator" "$threshold"; then
            satisfied_conditions=$((satisfied_conditions + 1))
            log::debug "Condition satisfied for node $node_name: $metric $operator $threshold (value: $metric_value)"
        else
            log::debug "Condition not satisfied for node $node_name: $metric $operator $threshold (value: $metric_value)"
        fi
    done
    
    # 根据逻辑判断是否触发
    if [[ "$condition_logic" == "AND" ]]; then
        [[ $satisfied_conditions -eq $condition_count ]]
    else  # OR
        [[ $satisfied_conditions -gt 0 ]]
    fi
}

# 执行规则动作
hook::execute_rule_actions() {
    local rule_object="$1"
    local triggered_nodes="$2"
    local rule_name=$(echo "$rule_object" | jq -r '.metadata.name')
    local actions=$(echo "$rule_object" | jq -r '.spec.actions')
    
    log::info "Executing actions for rule: $rule_name on nodes: $triggered_nodes"
    
    local action_count=$(echo "$actions" | jq 'length')
    for ((i=0; i<action_count; i++)); do
        local action=$(echo "$actions" | jq -r ".[$i]")
        local action_type=$(echo "$action" | jq -r '.type')
        
        case "$action_type" in
            "taint")
                hook::execute_taint_action "$action" "$triggered_nodes"
                ;;
            "alert")
                hook::execute_alert_action "$action" "$rule_object" "$triggered_nodes"
                ;;
            "evict")
                hook::execute_evict_action "$action" "$triggered_nodes"
                ;;
            "label")
                hook::execute_label_action "$action" "$triggered_nodes"
                ;;
            "annotation")
                hook::execute_annotation_action "$action" "$triggered_nodes"
                ;;
            *)
                log::warn "Unknown action type: $action_type"
                ;;
        esac
    done
    
    # 设置冷却期
    local cooldown_period=$(echo "$rule_object" | jq -r '.spec.monitoring.cooldownPeriod // "5m"')
    for node_name in $(echo "$triggered_nodes" | jq -r '.[]'); do
        cooldown::set "$rule_name" "$node_name"
    done
}

# 执行污点动作
hook::execute_taint_action() {
    local action="$1"
    local triggered_nodes="$2"
    
    local taint_key=$(echo "$action" | jq -r '.taint.key // "nodeguardian/rule-triggered"')
    local taint_value=$(echo "$action" | jq -r '.taint.value // "true"')
    local taint_effect=$(echo "$action" | jq -r '.taint.effect // "NoSchedule"')
    
    for node_name in $(echo "$triggered_nodes" | jq -r '.[]'); do
        log::info "Adding taint to node $node_name: $taint_key=$taint_value:$taint_effect"
        kubectl taint nodes "$node_name" "$taint_key=$taint_value:$taint_effect" --overwrite || true
    done
}

# 执行告警动作
hook::execute_alert_action() {
    local action="$1"
    local rule_object="$2"
    local triggered_nodes="$3"
    
    local alert_enabled=$(echo "$action" | jq -r '.alert.enabled // true')
    if [[ "$alert_enabled" != "true" ]]; then
        return 0
    fi
    
    local template_name=$(echo "$action" | jq -r '.alert.template // "default"')
    local channels=$(echo "$action" | jq -r '.alert.channels // []')
    
    # 调用告警管理器
    /hooks/002-alert-manager.sh "$template_name" "$rule_object" "$triggered_nodes" "$channels" || true
}

# 执行驱逐动作
hook::execute_evict_action() {
    local action="$1"
    local triggered_nodes="$2"
    
    local max_pods=$(echo "$action" | jq -r '.evict.maxPods // 10')
    local exclude_namespaces=$(echo "$action" | jq -r '.evict.excludeNamespaces // ["kube-system", "kube-public"]')
    
    for node_name in $(echo "$triggered_nodes" | jq -r '.[]'); do
        log::info "Evicting pods from node $node_name (max: $max_pods)"
        
        # 获取节点上的Pod
        local pods=$(kubectl get pods --all-namespaces -o json --field-selector spec.nodeName="$node_name" | \
            jq -r --argjson exclude "$exclude_namespaces" \
            '.items[] | select(.metadata.namespace as $ns | $exclude | index($ns) == null) | "\(.metadata.namespace)/\(.metadata.name)"')
        
        local evicted_count=0
        for pod in $pods; do
            if [[ $evicted_count -ge $max_pods ]]; then
                break
            fi
            
            log::info "Evicting pod: $pod"
            kubectl delete pod "$pod" --grace-period=30 || true
            evicted_count=$((evicted_count + 1))
        done
    done
}

# 执行标签动作
hook::execute_label_action() {
    local action="$1"
    local triggered_nodes="$2"
    
    local labels=$(echo "$action" | jq -r '.label.labels // {}')
    
    for node_name in $(echo "$triggered_nodes" | jq -r '.[]'); do
        log::info "Adding labels to node $node_name: $labels"
        
        local label_args=""
        for key in $(echo "$labels" | jq -r 'keys[]'); do
            local value=$(echo "$labels" | jq -r ".[\"$key\"]")
            label_args="$label_args $key=$value"
        done
        
        if [[ -n "$label_args" ]]; then
            kubectl label nodes "$node_name" $label_args --overwrite || true
        fi
    done
}

# 执行注解动作
hook::execute_annotation_action() {
    local action="$1"
    local triggered_nodes="$2"
    
    local annotations=$(echo "$action" | jq -r '.annotation.annotations // {}')
    
    for node_name in $(echo "$triggered_nodes" | jq -r '.[]'); do
        log::info "Adding annotations to node $node_name: $annotations"
        
        local annotation_args=""
        for key in $(echo "$annotations" | jq -r 'keys[]'); do
            local value=$(echo "$annotations" | jq -r ".[\"$key\"]")
            annotation_args="$annotation_args $key=$value"
        done
        
        if [[ -n "$annotation_args" ]]; then
            kubectl annotate nodes "$node_name" $annotation_args --overwrite || true
        fi
    done
}

# 创建命名空间
hook::create_namespace_if_not_exists() {
    local namespace=$(config::get "namespace")
    if ! kubectl get namespace "$namespace" >/dev/null 2>&1; then
        log::info "Creating namespace: $namespace"
        kubectl create namespace "$namespace"
    fi
}

# 创建配置映射
hook::create_configmap_if_not_exists() {
    local namespace=$(config::get "namespace")
    if ! kubectl get configmap "nodeguardian-config" -n "$namespace" >/dev/null 2>&1; then
        log::info "Creating configmap: nodeguardian-config"
        kubectl create configmap "nodeguardian-config" \
            --from-literal=prometheus_url="$(config::get "prometheus_url")" \
            --from-literal=metrics_server_url="$(config::get "metrics_server_url")" \
            --from-literal=log_level="$(config::get "log_level")" \
            -n "$namespace"
    fi
}

# 初始化现有规则
hook::initialize_existing_rules() {
    log::info "Initializing existing NodeGuardianRule objects..."
    # 这里会在同步阶段处理
    return 0
}

# 调用公共运行函数
common::run_hook "$@"