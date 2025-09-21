#!/usr/bin/env bash

# NodeGuardian Alert Manager Hook
# 处理告警模板渲染和发送

set -euo pipefail

# 加载公共函数库
source /hooks/common/functions.sh

# 配置目录
CONFIG_DIR="/etc/nodeguardian/config"
SECRETS_DIR="/etc/nodeguardian/secrets"
CONFIG_FILE="$CONFIG_DIR/config.json"

# 加载统一配置文件
hook::load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        cat "$CONFIG_FILE"
    else
        # 返回默认配置
        cat <<EOF
{
  "email": {
    "smtpServer": "smtp.gmail.com",
    "smtpPort": 587,
    "useTLS": true,
    "useSSL": false
  },
  "prometheus": {
    "url": "http://prometheus-k8s.monitoring.svc:9090",
    "timeout": "30s"
  },
  "alert": {
    "defaultChannels": ["log", "email"],
    "retryAttempts": 3
  },
  "monitoring": {
    "defaultCheckInterval": "30s",
    "defaultCooldownPeriod": "10m"
  }
}
EOF
    fi
}

# 加载Secret配置
hook::load_secret() {
    local secret_file="$1"
    
    if [[ -f "$SECRETS_DIR/$secret_file" ]]; then
        cat "$SECRETS_DIR/$secret_file"
    else
        echo ""
    fi
}

# 初始化配置
hook::init_config() {
    # 加载统一配置文件
    local full_config=$(hook::load_config)
    
    # 加载Secret中的敏感信息
    local email_username=$(hook::load_secret "email-username")
    local email_password=$(hook::load_secret "email-password")
    local webhook_url=$(hook::load_secret "webhook-url")
    
    # 合并敏感信息到配置中
    if [[ -n "$email_username" ]]; then
        full_config=$(echo "$full_config" | jq --arg username "$email_username" '.email.username = $username')
    fi
    
    if [[ -n "$email_password" ]]; then
        full_config=$(echo "$full_config" | jq --arg password "$email_password" '.email.password = $password')
    fi
    
    if [[ -n "$webhook_url" ]]; then
        full_config=$(echo "$full_config" | jq --arg url "$webhook_url" '.alert.webhookUrl = $url')
    fi
    
    # 设置环境变量
    export NODEGUARDIAN_CONFIG="$full_config"
    export NODEGUARDIAN_EMAIL_CONFIG=$(echo "$full_config" | jq -c '.email')
    export NODEGUARDIAN_WEBHOOK_URL=$(echo "$full_config" | jq -r '.alert.webhookUrl // ""')
    export NODEGUARDIAN_PROMETHEUS_CONFIG=$(echo "$full_config" | jq -c '.prometheus')
    export NODEGUARDIAN_ALERT_CONFIG=$(echo "$full_config" | jq -c '.alert')
    export NODEGUARDIAN_MONITORING_CONFIG=$(echo "$full_config" | jq -c '.monitoring')
    
    log::info "Configuration loaded successfully"
}

# Hook配置函数
hook::config() {
    cat <<EOF
{
  "configVersion": "v1",
  "kubernetes": [
    {
      "name": "monitor-alert-templates",
      "apiVersion": "nodeguardian.k8s.io/v1",
      "kind": "AlertTemplate",
      "executeHookOnEvent": ["Added", "Modified", "Deleted"],
      "executeHookOnSynchronization": true,
      "queue": "alert-templates"
    }
  ]
}
EOF
}

# Hook触发函数
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

# 处理模板事件
hook::handle_template_event() {
    local binding_context_path="$1"
    local watch_event=$(jq -r '.[0].watchEvent' "$binding_context_path")
    local template_object=$(jq -r '.[0].object' "$binding_context_path")
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

# 处理直接调用
hook::handle_direct_call() {
    local template_name="${1:-default}"
    local rule_object="${2:-{}}"
    local triggered_nodes="${3:-[]}"
    local channels="${4:-[]}"
    
    log::info "Processing direct alert call: template=$template_name, nodes=$triggered_nodes"
    
    hook::send_alert "$template_name" "$rule_object" "$triggered_nodes" "$channels"
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

# 发送告警
hook::send_alert() {
    local template_name="$1"
    local rule_object="$2"
    local triggered_nodes="$3"
    local channels="$4"
    
    # 获取模板
    local template_file="/tmp/nodeguardian/templates/${template_name}.json"
    if [[ ! -f "$template_file" ]]; then
        log::warn "Alert template not found: $template_name, using default"
        hook::create_default_template "$template_name"
    fi
    
    local template_object=$(cat "$template_file")
    
    # 渲染告警内容
    local alert_content=$(hook::render_alert_content "$template_object" "$rule_object" "$triggered_nodes")
    
    # 发送到各个渠道
    hook::send_to_channels "$alert_content" "$channels" "$template_object"
}

# 创建默认模板
hook::create_default_template() {
    local template_name="$1"
    local template_file="/tmp/nodeguardian/templates/${template_name}.json"
    
    local default_template=$(cat <<EOF
{
  "metadata": {
    "name": "$template_name"
  },
  "spec": {
    "title": "NodeGuardian Alert",
    "summary": "NodeGuardian rule triggered",
    "description": "Rule {{.ruleName}} has been triggered on nodes: {{.triggeredNodes}}",
    "severity": "warning",
    "channels": [
      {
        "type": "log",
        "enabled": true
      }
    ]
  }
}
EOF
)
    
    mkdir -p "$(dirname "$template_file")"
    echo "$default_template" > "$template_file"
}

# 渲染告警内容
hook::render_alert_content() {
    local template_object="$1"
    local rule_object="$2"
    local triggered_nodes="$3"
    
    # 检查是否是恢复告警
    local alert_type=$(echo "$rule_object" | jq -r '.type // "trigger"')
    
    local rule_name=$(echo "$rule_object" | jq -r '.metadata.name // "unknown"')
    local rule_description=$(echo "$rule_object" | jq -r '.spec.metadata.description // "No description"')
    local rule_severity=$(echo "$rule_object" | jq -r '.spec.metadata.severity // "warning"')
    
    # 获取模板字段
    local title=$(echo "$template_object" | jq -r '.spec.title // "NodeGuardian Alert"')
    local summary=$(echo "$template_object" | jq -r '.spec.summary // "Rule triggered"')
    local description=$(echo "$template_object" | jq -r '.spec.description // "Rule {{.ruleName}} triggered"')
    local severity=$(echo "$template_object" | jq -r '.spec.severity // "warning"')
    
    # 如果是恢复告警，使用恢复相关的默认值
    if [[ "$alert_type" == "recovery" ]]; then
        title=$(echo "$template_object" | jq -r '.spec.title // "NodeGuardian Recovery Alert"')
        summary=$(echo "$template_object" | jq -r '.spec.summary // "Node recovered"')
        description=$(echo "$template_object" | jq -r '.spec.description // "Node {{.triggeredNodes}} has recovered from rule {{.ruleName}}"')
        severity=$(echo "$template_object" | jq -r '.spec.severity // "info"')
    fi
    
    # 简单的模板替换
    local rendered_title=$(echo "$title" | sed "s/{{\.ruleName}}/$rule_name/g")
    local rendered_summary=$(echo "$summary" | sed "s/{{\.ruleName}}/$rule_name/g")
    local rendered_description=$(echo "$description" | sed "s/{{\.ruleName}}/$rule_name/g" | sed "s/{{\.triggeredNodes}}/$triggered_nodes/g")
    
    # 构建告警内容
    local alert_content=$(cat <<EOF
{
  "title": "$rendered_title",
  "summary": "$rendered_summary",
  "description": "$rendered_description",
  "severity": "$severity",
  "ruleName": "$rule_name",
  "ruleDescription": "$rule_description",
  "triggeredNodes": $triggered_nodes,
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)
    
    echo "$alert_content"
}

# 发送到各个渠道
hook::send_to_channels() {
    local alert_content="$1"
    local channels="$2"
    local template_object="$3"
    
    # 获取模板中的默认渠道
    local template_channels=$(echo "$template_object" | jq -r '.spec.channels // []')
    
    # 合并渠道
    local all_channels=$(echo "$channels $template_channels" | jq -s 'add | unique')
    local channel_count=$(echo "$all_channels" | jq 'length')
    
    for ((i=0; i<channel_count; i++)); do
        local channel=$(echo "$all_channels" | jq -r ".[$i]")
        local channel_type=$(echo "$channel" | jq -r '.type')
        local channel_enabled=$(echo "$channel" | jq -r '.enabled // true')
        
        if [[ "$channel_enabled" == "true" ]]; then
            hook::send_to_channel "$channel_type" "$channel" "$alert_content"
        fi
    done
}

# 发送到单个渠道
hook::send_to_channel() {
    local channel_type="$1"
    local channel_config="$2"
    local alert_content="$3"
    
    case "$channel_type" in
        "log")
            hook::send_to_log "$alert_content"
            ;;
        "webhook")
            hook::send_to_webhook "$channel_config" "$alert_content"
            ;;
        "email")
            hook::send_to_email "$channel_config" "$alert_content"
            ;;
        *)
            log::warn "Unknown channel type: $channel_type"
            ;;
    esac
}

# 发送到日志
hook::send_to_log() {
    local alert_content="$1"
    local title=$(echo "$alert_content" | jq -r '.title')
    local summary=$(echo "$alert_content" | jq -r '.summary')
    local severity=$(echo "$alert_content" | jq -r '.severity')
    local rule_name=$(echo "$alert_content" | jq -r '.ruleName')
    local triggered_nodes=$(echo "$alert_content" | jq -r '.triggeredNodes')
    
    log::info "ALERT [$severity] $title - $summary"
    log::info "Rule: $rule_name, Nodes: $triggered_nodes"
}

# 发送到Webhook
hook::send_to_webhook() {
    local channel_config="$1"
    local alert_content="$2"
    
    local webhook_url
    local webhook_headers
    
    if [[ -n "$channel_config" && "$channel_config" != "null" ]]; then
        # 使用传入的配置
        webhook_url=$(echo "$channel_config" | jq -r '.url')
        webhook_headers=$(echo "$channel_config" | jq -r '.headers // {}')
    elif [[ -n "${NODEGUARDIAN_WEBHOOK_URL:-}" ]]; then
        # 使用ConfigMap中的配置
        webhook_url="$NODEGUARDIAN_WEBHOOK_URL"
        webhook_headers="{}"
    else
        # 从环境变量获取（向后兼容）
        webhook_url="${ALERT_WEBHOOK_URL:-}"
        webhook_headers="{}"
    fi
    
    if [[ -z "$webhook_url" ]]; then
        log::warn "Webhook URL not configured"
        return 1
    fi
    
    log::info "Sending alert to webhook: $webhook_url"
    
    # 构建curl命令
    local curl_cmd="curl -s -X POST '$webhook_url'"
    
    # 添加headers
    for key in $(echo "$webhook_headers" | jq -r 'keys[]'); do
        local value=$(echo "$webhook_headers" | jq -r ".[\"$key\"]")
        curl_cmd="$curl_cmd -H '$key: $value'"
    done
    
    # 添加Content-Type
    curl_cmd="$curl_cmd -H 'Content-Type: application/json'"
    
    # 发送数据
    curl_cmd="$curl_cmd -d '$alert_content'"
    
    # 执行请求
    eval "$curl_cmd" || log::error "Failed to send webhook alert"
}

# 发送到邮件
hook::send_to_email() {
    local channel_config="$1"
    local alert_content="$2"
    
    # 检查Python脚本是否存在
    local email_script="/scripts/sendmail.py"
    if [[ ! -f "$email_script" ]]; then
        log::error "Email script not found: $email_script"
        return 1
    fi
    
    # 检查Python是否可用
    if ! command -v python3 >/dev/null 2>&1; then
        log::error "Python3 not available, cannot send email"
        return 1
    fi
    
    log::info "Sending alert via email"
    
    # 调用Python邮件发送脚本（使用统一配置）
    if python3 "$email_script" \
        --alert-data "$alert_content" \
        --format "html"; then
        log::info "Email sent successfully"
    else
        log::error "Failed to send email"
        return 1
    fi
}

# 初始化配置
hook::init_config

# 调用公共运行函数
common::run_hook "$@"
