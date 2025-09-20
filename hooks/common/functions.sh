#!/usr/bin/env bash

# NodeGuardian Common Functions Library
# 提供标准的hook运行函数和工具函数

set -euo pipefail

# 标准hook运行函数
common::run_hook() {
    if [[ $1 == "--config" ]]; then
        hook::config
    else
        hook::trigger
    fi
}

# 日志函数
log::info() {
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [INFO] $message" >&2
}

log::warn() {
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [WARN] $message" >&2
}

log::error() {
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [ERROR] $message" >&2
}

log::debug() {
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    if [[ "${LOG_LEVEL:-INFO}" == "DEBUG" ]]; then
        echo "[$timestamp] [DEBUG] $message" >&2
    fi
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

validate::file_exists() {
    local file_path="$1"
    
    if [[ ! -f "$file_path" ]]; then
        log::error "File not found: $file_path"
        exit 1
    fi
}

# Kubernetes工具函数
kubectl::replace_or_create() {
    local object="$1"
    
    if ! kubectl get -f - <<< "$object" >/dev/null 2>/dev/null; then
        kubectl create -f - <<< "$object" >/dev/null
        log::info "Created Kubernetes object"
    else
        kubectl replace --force -f - <<< "$object" >/dev/null
        log::info "Updated Kubernetes object"
    fi
}

kubectl::apply() {
    local object="$1"
    
    kubectl apply -f - <<< "$object" >/dev/null
    log::info "Applied Kubernetes object"
}

kubectl::delete() {
    local object="$1"
    
    kubectl delete -f - <<< "$object" >/dev/null 2>&1 || true
    log::info "Deleted Kubernetes object"
}

# 配置管理函数
config::get() {
    local key="$1"
    local default_value="${2:-}"
    
    case "$key" in
        "namespace")
            echo "${NODEGUARDIAN_NAMESPACE:-nodeguardian-system}"
            ;;
        "log_level")
            echo "${LOG_LEVEL:-INFO}"
            ;;
        "prometheus_url")
            echo "${PROMETHEUS_URL:-http://prometheus-k8s.monitoring.svc:9090}"
            ;;
        "metrics_server_url")
            echo "${METRICS_SERVER_URL:-https://kubernetes.default.svc:443/apis/metrics.k8s.io/v1beta1}"
            ;;
        *)
            echo "$default_value"
            ;;
    esac
}

# 指标收集函数
metrics::get_node_cpu_utilization() {
    local node_name="$1"
    local prometheus_url=$(config::get "prometheus_url")
    
    # 尝试从Prometheus获取
    if [[ -n "$prometheus_url" ]]; then
        local query="100 - (avg by (instance) (irate(node_cpu_seconds_total{mode=\"idle\",instance=~\".*$node_name.*\"}[5m])) * 100)"
        local result=$(curl -s "${prometheus_url}/api/v1/query" \
            --data-urlencode "query=$query" | \
            jq -r '.data.result[0].value[1] // empty' 2>/dev/null)
        
        if [[ -n "$result" ]]; then
            echo "$result"
            return 0
        fi
    fi
    
    # 从Metrics Server获取
    local metrics_server_url=$(config::get "metrics_server_url")
    local cpu_usage=$(kubectl get --raw "${metrics_server_url}/nodes/$node_name" 2>/dev/null | \
        jq -r '.usage.cpu' | \
        sed 's/m//' | \
        awk '{print $1/1000}')  # 转换为核数
    
    local cpu_capacity=$(kubectl get node "$node_name" -o jsonpath='{.status.capacity.cpu}')
    
    if [[ -n "$cpu_usage" && -n "$cpu_capacity" ]]; then
        local utilization=$(echo "scale=2; $cpu_usage * 100 / $cpu_capacity" | bc -l)
        echo "$utilization"
    else
        echo "0"
    fi
}

metrics::get_node_memory_utilization() {
    local node_name="$1"
    local prometheus_url=$(config::get "prometheus_url")
    
    # 尝试从Prometheus获取
    if [[ -n "$prometheus_url" ]]; then
        local query="(1 - (node_memory_MemAvailable_bytes{instance=~\".*$node_name.*\"} / node_memory_MemTotal_bytes{instance=~\".*$node_name.*\"})) * 100"
        local result=$(curl -s "${prometheus_url}/api/v1/query" \
            --data-urlencode "query=$query" | \
            jq -r '.data.result[0].value[1] // empty' 2>/dev/null)
        
        if [[ -n "$result" ]]; then
            echo "$result"
            return 0
        fi
    fi
    
    # 从Metrics Server获取
    local metrics_server_url=$(config::get "metrics_server_url")
    local memory_usage=$(kubectl get --raw "${metrics_server_url}/nodes/$node_name" 2>/dev/null | \
        jq -r '.usage.memory' | \
        sed 's/Ki//' | \
        awk '{print $1/1024/1024}')  # 转换为GB
    
    local memory_capacity=$(kubectl get node "$node_name" -o jsonpath='{.status.capacity.memory}' | \
        sed 's/Ki//' | \
        awk '{print $1/1024/1024}')  # 转换为GB
    
    if [[ -n "$memory_usage" && -n "$memory_capacity" ]]; then
        local utilization=$(echo "scale=2; $memory_usage * 100 / $memory_capacity" | bc -l)
        echo "$utilization"
    else
        echo "0"
    fi
}

metrics::get_node_disk_utilization() {
    local node_name="$1"
    local prometheus_url=$(config::get "prometheus_url")
    
    # 从Prometheus获取
    if [[ -n "$prometheus_url" ]]; then
        local query="(1 - (node_filesystem_avail_bytes{instance=~\".*$node_name.*\",mountpoint=\"/\"} / node_filesystem_size_bytes{instance=~\".*$node_name.*\",mountpoint=\"/\"})) * 100"
        local result=$(curl -s "${prometheus_url}/api/v1/query" \
            --data-urlencode "query=$query" | \
            jq -r '.data.result[0].value[1] // empty' 2>/dev/null)
        
        if [[ -n "$result" ]]; then
            echo "$result"
            return 0
        fi
    fi
    
    # 从节点状态获取（备用方案）
    local disk_usage=$(kubectl get node "$node_name" -o jsonpath='{.status.conditions[?(@.type=="DiskPressure")].status}')
    if [[ "$disk_usage" == "True" ]]; then
        echo "90"  # 假设磁盘压力时使用率为90%
    else
        echo "0"
    fi
}

metrics::get_node_cpu_load_ratio() {
    local node_name="$1"
    local prometheus_url=$(config::get "prometheus_url")
    
    # 从Prometheus获取
    if [[ -n "$prometheus_url" ]]; then
        local query="node_load1{instance=~\".*$node_name.*\"} / on(instance) count by (instance) (node_cpu_seconds_total{mode=\"idle\",instance=~\".*$node_name.*\"})"
        local result=$(curl -s "${prometheus_url}/api/v1/query" \
            --data-urlencode "query=$query" | \
            jq -r '.data.result[0].value[1] // empty' 2>/dev/null)
        
        if [[ -n "$result" ]]; then
            echo "$result"
            return 0
        fi
    fi
    
    # 备用方案：基于CPU使用率估算
    local cpu_util=$(metrics::get_node_cpu_utilization "$node_name")
    local load_ratio=$(echo "scale=2; $cpu_util / 100" | bc -l)
    echo "$load_ratio"
}

# 条件评估函数
condition::evaluate() {
    local metric_value="$1"
    local operator="$2"
    local threshold="$3"
    
    case "$operator" in
        "GreaterThan")
            [[ $(echo "$metric_value > $threshold" | bc -l) -eq 1 ]]
            ;;
        "LessThan")
            [[ $(echo "$metric_value < $threshold" | bc -l) -eq 1 ]]
            ;;
        "EqualTo")
            [[ $(echo "$metric_value == $threshold" | bc -l) -eq 1 ]]
            ;;
        "NotEqualTo")
            [[ $(echo "$metric_value != $threshold" | bc -l) -eq 1 ]]
            ;;
        "GreaterThanOrEqual")
            [[ $(echo "$metric_value >= $threshold" | bc -l) -eq 1 ]]
            ;;
        "LessThanOrEqual")
            [[ $(echo "$metric_value <= $threshold" | bc -l) -eq 1 ]]
            ;;
        *)
            log::error "Unknown operator: $operator"
            return 1
            ;;
    esac
}

# 持续时间解析函数
duration::parse() {
    local duration="$1"
    local seconds=0
    
    if [[ "$duration" =~ ^([0-9]+)s$ ]]; then
        seconds=${BASH_REMATCH[1]}
    elif [[ "$duration" =~ ^([0-9]+)m$ ]]; then
        seconds=$((${BASH_REMATCH[1]} * 60))
    elif [[ "$duration" =~ ^([0-9]+)h$ ]]; then
        seconds=$((${BASH_REMATCH[1]} * 3600))
    elif [[ "$duration" =~ ^([0-9]+)d$ ]]; then
        seconds=$((${BASH_REMATCH[1]} * 86400))
    else
        log::error "Invalid duration format: $duration"
        return 1
    fi
    
    echo "$seconds"
}

# 冷却期管理函数
cooldown::check() {
    local rule_name="$1"
    local node_name="$2"
    local cooldown_period="$3"
    local cooldown_file="/tmp/nodeguardian/cooldown/${rule_name}_${node_name}"
    
    if [[ -f "$cooldown_file" ]]; then
        local last_triggered=$(cat "$cooldown_file")
        local current_time=$(date +%s)
        local cooldown_seconds=$(duration::parse "$cooldown_period")
        
        if [[ $((current_time - last_triggered)) -lt $cooldown_seconds ]]; then
            return 0  # 仍在冷却期内
        fi
    fi
    
    return 1  # 不在冷却期内
}

cooldown::set() {
    local rule_name="$1"
    local node_name="$2"
    local cooldown_file="/tmp/nodeguardian/cooldown/${rule_name}_${node_name}"
    
    mkdir -p "$(dirname "$cooldown_file")"
    date +%s > "$cooldown_file"
}

# 节点选择器函数
node::get_matching() {
    local node_selector="$1"
    
    if [[ -n "$(echo "$node_selector" | jq -r '.nodeNames // empty')" ]]; then
        # 直接指定节点名称
        echo "$node_selector" | jq -r '.nodeNames[]'
    else
        # 使用标签选择器
        local label_selector=""
        if [[ -n "$(echo "$node_selector" | jq -r '.matchLabels // empty')" ]]; then
            local labels=$(echo "$node_selector" | jq -r '.matchLabels | to_entries[] | "\(.key)=\(.value)"' | tr '\n' ',' | sed 's/,$//')
            label_selector="--selector=$labels"
        fi
        
        kubectl get nodes $label_selector -o jsonpath='{.items[*].metadata.name}'
    fi
}

# 规则状态更新函数
rule::update_status() {
    local rule_name="$1"
    local phase="$2"
    local message="$3"
    local triggered_nodes="$4"
    
    local status_patch=$(cat <<EOF
{
  "status": {
    "phase": "$phase",
    "lastTriggered": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "triggeredNodes": $triggered_nodes,
    "lastError": "$message"
  }
}
EOF
)
    
    kubectl patch nodeguardianrule "$rule_name" --type=merge --patch="$status_patch" || true
}

# 初始化函数
init::nodeguardian() {
    log::info "Initializing NodeGuardian..."
    
    # 检查必要的命令
    local commands=("kubectl" "jq" "curl" "bc")
    for cmd in "${commands[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            log::error "Command '$cmd' not found"
            exit 1
        fi
    done
    
    # 创建必要的目录
    mkdir -p "/tmp/nodeguardian/cooldown"
    mkdir -p "/tmp/nodeguardian/state"
    mkdir -p "/tmp/nodeguardian/rules"
    mkdir -p "/tmp/nodeguardian/templates"
    
    log::info "NodeGuardian initialized successfully"
}