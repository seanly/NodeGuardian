#!/usr/bin/env bash

# NodeGuardian Alert Manager Hook
# 处理告警模板渲染和发送

set -euo pipefail

# 加载公共函数库
source /hooks/common/functions.sh

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
    
    # 读取绑定上下文
    local binding_context_path="${BINDING_CONTEXT_PATH:-/tmp/binding_context.json}"
    validate::file_exists "$binding_context_path"
    
    # 处理绑定上下文
    local context_type=$(jq -r '.[0].type' "$binding_context_path")
    local binding=$(jq -r '.[0].binding' "$binding_context_path")
    
    log::info "Alert manager processing: type=$context_type, binding=$binding"
    
    case "$context_type" in
        "Synchronization")
            hook::handle_templates_synchronization
            ;;
        "Event")
            hook::handle_template_event "$binding_context_path"
            ;;
        *)
            # 处理直接调用（从控制器调用）
            hook::handle_direct_call "$@"
            ;;
    esac
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
        "slack")
            hook::send_to_slack "$channel_config" "$alert_content"
            ;;
        "teams")
            hook::send_to_teams "$channel_config" "$alert_content"
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
    
    local webhook_url=$(echo "$channel_config" | jq -r '.url')
    local webhook_headers=$(echo "$channel_config" | jq -r '.headers // {}')
    
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
    
    local smtp_server=$(echo "$channel_config" | jq -r '.smtpServer')
    local smtp_port=$(echo "$channel_config" | jq -r '.smtpPort // 587')
    local username=$(echo "$channel_config" | jq -r '.username')
    local password=$(echo "$channel_config" | jq -r '.password')
    local from=$(echo "$channel_config" | jq -r '.from')
    local to=$(echo "$channel_config" | jq -r '.to')
    
    if [[ -z "$smtp_server" || -z "$from" || -z "$to" ]]; then
        log::warn "Email configuration incomplete"
        return 1
    fi
    
    log::info "Sending alert to email: $to"
    
    local title=$(echo "$alert_content" | jq -r '.title')
    local summary=$(echo "$alert_content" | jq -r '.summary')
    local description=$(echo "$alert_content" | jq -r '.description')
    
    # 使用mail命令发送邮件（需要安装mailutils）
    if command -v mail >/dev/null 2>&1; then
        echo "$description" | mail -s "$title" "$to" || log::error "Failed to send email alert"
    else
        log::warn "mail command not available, skipping email alert"
    fi
}

# 发送到Slack
hook::send_to_slack() {
    local channel_config="$1"
    local alert_content="$2"
    
    local webhook_url=$(echo "$channel_config" | jq -r '.webhookUrl')
    local channel=$(echo "$channel_config" | jq -r '.channel // "#alerts"')
    local username=$(echo "$channel_config" | jq -r '.username // "NodeGuardian"')
    
    if [[ -z "$webhook_url" ]]; then
        log::warn "Slack webhook URL not configured"
        return 1
    fi
    
    log::info "Sending alert to Slack channel: $channel"
    
    local title=$(echo "$alert_content" | jq -r '.title')
    local summary=$(echo "$alert_content" | jq -r '.summary')
    local severity=$(echo "$alert_content" | jq -r '.severity')
    local rule_name=$(echo "$alert_content" | jq -r '.ruleName')
    local triggered_nodes=$(echo "$alert_content" | jq -r '.triggeredNodes')
    
    # 根据严重程度选择颜色
    local color="warning"
    case "$severity" in
        "critical"|"error")
            color="danger"
            ;;
        "warning")
            color="warning"
            ;;
        "info")
            color="good"
            ;;
    esac
    
    local slack_payload=$(cat <<EOF
{
  "channel": "$channel",
  "username": "$username",
  "attachments": [
    {
      "color": "$color",
      "title": "$title",
      "text": "$summary",
      "fields": [
        {
          "title": "Rule",
          "value": "$rule_name",
          "short": true
        },
        {
          "title": "Nodes",
          "value": "$triggered_nodes",
          "short": true
        }
      ],
      "timestamp": $(date +%s)
    }
  ]
}
EOF
)
    
    curl -s -X POST "$webhook_url" \
        -H 'Content-Type: application/json' \
        -d "$slack_payload" || log::error "Failed to send Slack alert"
}

# 发送到Teams
hook::send_to_teams() {
    local channel_config="$1"
    local alert_content="$2"
    
    local webhook_url=$(echo "$channel_config" | jq -r '.webhookUrl')
    
    if [[ -z "$webhook_url" ]]; then
        log::warn "Teams webhook URL not configured"
        return 1
    fi
    
    log::info "Sending alert to Microsoft Teams"
    
    local title=$(echo "$alert_content" | jq -r '.title')
    local summary=$(echo "$alert_content" | jq -r '.summary')
    local severity=$(echo "$alert_content" | jq -r '.severity')
    local rule_name=$(echo "$alert_content" | jq -r '.ruleName')
    local triggered_nodes=$(echo "$alert_content" | jq -r '.triggeredNodes')
    
    # 根据严重程度选择颜色
    local color="FFA500"  # 橙色
    case "$severity" in
        "critical"|"error")
            color="FF0000"  # 红色
            ;;
        "warning")
            color="FFA500"  # 橙色
            ;;
        "info")
            color="00FF00"  # 绿色
            ;;
    esac
    
    local teams_payload=$(cat <<EOF
{
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "themeColor": "$color",
  "summary": "$title",
  "sections": [
    {
      "activityTitle": "$title",
      "activitySubtitle": "$summary",
      "facts": [
        {
          "name": "Rule",
          "value": "$rule_name"
        },
        {
          "name": "Severity",
          "value": "$severity"
        },
        {
          "name": "Nodes",
          "value": "$triggered_nodes"
        }
      ],
      "markdown": true
    }
  ]
}
EOF
)
    
    curl -s -X POST "$webhook_url" \
        -H 'Content-Type: application/json' \
        -d "$teams_payload" || log::error "Failed to send Teams alert"
}

# 调用公共运行函数
common::run_hook "$@"
