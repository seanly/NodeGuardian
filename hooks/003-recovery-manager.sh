#!/usr/bin/env bash

# NodeGuardian Recovery Manager Hook
# 处理节点恢复逻辑和恢复动作执行

set -euo pipefail

# 加载公共函数库
source /hooks/common/functions.sh

# Hook配置函数
hook::config() {
    cat <<EOF
{
  "configVersion": "v1",
  "schedule": [
    {
      "name": "recovery-check",
      "crontab": "*/2 * * * *",
      "queue": "recovery-check",
      "includeSnapshotsFrom": ["monitor-nodeguardian-rules"]
    }
  ]
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
    
    log::info "Recovery manager processing: type=$context_type, binding=$binding"
    
    case "$context_type" in
        "Schedule")
            if [[ "$binding" == "recovery-check" ]]; then
                hook::check_recovery_conditions
            fi
            ;;
        *)
            log::warn "Unknown binding context type: $context_type"
            ;;
    esac
}

# 检查恢复条件
hook::check_recovery_conditions() {
    log::debug "Checking recovery conditions for all rules..."
    
    local rules_dir="/tmp/nodeguardian/rules"
    if [[ ! -d "$rules_dir" ]]; then
        return 0
    fi
    
    for rule_file in "$rules_dir"/*.json; do
        if [[ -f "$rule_file" ]]; then
            local rule_name=$(basename "$rule_file" .json)
            hook::check_rule_recovery "$rule_file"
        fi
    done
}

# 检查单个规则的恢复条件
hook::check_rule_recovery() {
    local rule_file="$1"
    local rule_object=$(cat "$rule_file")
    local rule_name=$(echo "$rule_object" | jq -r '.metadata.name')
    local rule_enabled=$(echo "$rule_object" | jq -r '.spec.metadata.enabled // true')
    
    if [[ "$rule_enabled" != "true" ]]; then
        return 0
    fi
    
    # 检查是否有恢复条件
    local recovery_conditions=$(echo "$rule_object" | jq -r '.spec.recoveryConditions // []')
    local recovery_conditions_count=$(echo "$recovery_conditions" | jq 'length')
    
    if [[ $recovery_conditions_count -eq 0 ]]; then
        return 0
    fi
    
    log::debug "Checking recovery conditions for rule: $rule_name"
    
    # 获取节点选择器
    local node_selector=$(echo "$rule_object" | jq -r '.spec.nodeSelector')
    local matching_nodes=$(node::get_matching "$node_selector")
    
    if [[ -z "$matching_nodes" ]]; then
        return 0
    fi
    
    # 检查每个节点的恢复条件
    for node_name in $matching_nodes; do
        if hook::check_node_recovery "$rule_object" "$node_name"; then
            hook::execute_recovery_actions "$rule_object" "$node_name"
        fi
    done
}

# 检查节点的恢复条件
hook::check_node_recovery() {
    local rule_object="$1"
    local node_name="$2"
    local rule_name=$(echo "$rule_object" | jq -r '.metadata.name')
    
    # 检查节点是否在触发状态
    if ! hook::is_node_triggered "$rule_name" "$node_name"; then
        return 1
    fi
    
    # 检查恢复冷却期
    local recovery_cooldown=$(echo "$rule_object" | jq -r '.spec.monitoring.recoveryCooldownPeriod // "2m"')
    if cooldown::check "${rule_name}_recovery" "$node_name" "$recovery_cooldown"; then
        log::debug "Node $node_name is in recovery cooldown period for rule $rule_name"
        return 1
    fi
    
    # 获取恢复条件
    local recovery_conditions=$(echo "$rule_object" | jq -r '.spec.recoveryConditions')
    local condition_logic=$(echo "$rule_object" | jq -r '.spec.recoveryConditionLogic // "AND"')
    
    local condition_count=$(echo "$recovery_conditions" | jq 'length')
    local satisfied_conditions=0
    
    # 评估每个恢复条件
    for ((i=0; i<condition_count; i++)); do
        local condition=$(echo "$recovery_conditions" | jq -r ".[$i]")
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
                log::error "Unknown recovery metric type: $metric"
                return 1
                ;;
        esac
        
        # 评估恢复条件
        if condition::evaluate "$metric_value" "$operator" "$threshold"; then
            satisfied_conditions=$((satisfied_conditions + 1))
            log::debug "Recovery condition satisfied for node $node_name: $metric $operator $threshold (value: $metric_value)"
        else
            log::debug "Recovery condition not satisfied for node $node_name: $metric $operator $threshold (value: $metric_value)"
        fi
    done
    
    # 根据逻辑判断是否满足恢复条件
    if [[ "$condition_logic" == "AND" ]]; then
        [[ $satisfied_conditions -eq $condition_count ]]
    else  # OR
        [[ $satisfied_conditions -gt 0 ]]
    fi
}

# 检查节点是否在触发状态
hook::is_node_triggered() {
    local rule_name="$1"
    local node_name="$2"
    
    # 检查是否有污点
    local taint_key="nodeguardian/rule-triggered"
    if kubectl describe node "$node_name" | grep -q "$taint_key"; then
        return 0
    fi
    
    # 检查是否有相关标签
    if kubectl get node "$node_name" -o jsonpath='{.metadata.labels}' | grep -q "nodeguardian.io/rule-triggered"; then
        return 0
    fi
    
    return 1
}

# 执行恢复动作
hook::execute_recovery_actions() {
    local rule_object="$1"
    local node_name="$2"
    local rule_name=$(echo "$rule_object" | jq -r '.metadata.name')
    
    log::info "Executing recovery actions for rule: $rule_name on node: $node_name"
    
    # 获取恢复动作
    local recovery_actions=$(echo "$rule_object" | jq -r '.spec.recoveryActions // []')
    local action_count=$(echo "$recovery_actions" | jq 'length')
    
    if [[ $action_count -eq 0 ]]; then
        log::info "No recovery actions defined for rule: $rule_name"
        return 0
    fi
    
    # 执行每个恢复动作
    for ((i=0; i<action_count; i++)); do
        local action=$(echo "$recovery_actions" | jq -r ".[$i]")
        local action_type=$(echo "$action" | jq -r '.type')
        
        case "$action_type" in
            "untaint")
                hook::execute_untaint_action "$action" "$node_name"
                ;;
            "removeLabel")
                hook::execute_remove_label_action "$action" "$node_name"
                ;;
            "removeAnnotation")
                hook::execute_remove_annotation_action "$action" "$node_name"
                ;;
            "alert")
                hook::execute_recovery_alert_action "$action" "$rule_object" "$node_name"
                ;;
            *)
                log::warn "Unknown recovery action type: $action_type"
                ;;
        esac
    done
    
    # 设置恢复冷却期
    local recovery_cooldown=$(echo "$rule_object" | jq -r '.spec.monitoring.recoveryCooldownPeriod // "2m"')
    cooldown::set "${rule_name}_recovery" "$node_name"
    
    # 更新规则状态
    hook::update_rule_recovery_status "$rule_name" "$node_name"
    
    log::info "Recovery actions completed for rule: $rule_name on node: $node_name"
}

# 执行去污点动作
hook::execute_untaint_action() {
    local action="$1"
    local node_name="$2"
    
    local taint_key=$(echo "$action" | jq -r '.untaint.key // "nodeguardian/rule-triggered"')
    local taint_value=$(echo "$action" | jq -r '.untaint.value // "true"')
    local taint_effect=$(echo "$action" | jq -r '.untaint.effect // "NoSchedule"')
    
    log::info "Removing taint from node $node_name: $taint_key=$taint_value:$taint_effect"
    kubectl taint nodes "$node_name" "$taint_key=$taint_value:$taint_effect" --overwrite || true
}

# 执行移除标签动作
hook::execute_remove_label_action() {
    local action="$1"
    local node_name="$2"
    
    local labels=$(echo "$action" | jq -r '.removeLabel.labels // []')
    local label_count=$(echo "$labels" | jq 'length')
    
    for ((i=0; i<label_count; i++)); do
        local label=$(echo "$labels" | jq -r ".[$i]")
        log::info "Removing label from node $node_name: $label"
        kubectl label nodes "$node_name" "$label-" || true
    done
}

# 执行移除注解动作
hook::execute_remove_annotation_action() {
    local action="$1"
    local node_name="$2"
    
    local annotations=$(echo "$action" | jq -r '.removeAnnotation.annotations // []')
    local annotation_count=$(echo "$annotations" | jq 'length')
    
    for ((i=0; i<annotation_count; i++)); do
        local annotation=$(echo "$annotations" | jq -r ".[$i]")
        log::info "Removing annotation from node $node_name: $annotation"
        kubectl annotate nodes "$node_name" "$annotation-" || true
    done
}

# 执行恢复告警动作
hook::execute_recovery_alert_action() {
    local action="$1"
    local rule_object="$2"
    local node_name="$3"
    
    local alert_enabled=$(echo "$action" | jq -r '.alert.enabled // true')
    if [[ "$alert_enabled" != "true" ]]; then
        return 0
    fi
    
    local template_name=$(echo "$action" | jq -r '.alert.template // "recovery"')
    local channels=$(echo "$action" | jq -r '.alert.channels // []')
    
    # 为规则对象添加恢复告警信息
    local recovery_rule_object=$(echo "$rule_object" | jq --arg node "$node_name" --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
        . + {
            "type": "recovery",
            "recoveryInfo": {
                "nodeName": $node,
                "timestamp": $timestamp,
                "message": "Node " + $node + " has recovered from rule " + .metadata.name
            }
        }
    ')
    
    # 调用告警管理器
    /hooks/002-alert-manager.sh "$template_name" "$recovery_rule_object" "[\"$node_name\"]" "$channels" || true
}

# 更新规则恢复状态
hook::update_rule_recovery_status() {
    local rule_name="$1"
    local node_name="$2"
    
    # 获取当前状态
    local current_status=$(kubectl get nodeguardianrule "$rule_name" -o jsonpath='{.status.triggeredNodes}' 2>/dev/null || echo "[]")
    local updated_nodes=$(echo "$current_status" | jq -r --arg node "$node_name" '. - [$node]')
    
    # 更新状态
    local status_patch=$(cat <<EOF
{
  "status": {
    "triggeredNodes": $updated_nodes,
    "lastRecovery": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  }
}
EOF
)
    
    kubectl patch nodeguardianrule "$rule_name" --type=merge --patch="$status_patch" || true
}

# 调用公共运行函数
common::run_hook "$@"
