"""Alert manager for sending notifications."""

import json
import smtplib
import requests
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from typing import Dict, Any, List, Optional
from jinja2 import Template
from .common import Logger, NodeGuardianConfig, KubernetesClient, MetricsCollector


class AlertManager:
    """Manages alert sending and template rendering."""
    
    def __init__(self, config: NodeGuardianConfig):
        self.config = config
        self.logger = Logger("alert-manager")
        self.k8s_client = KubernetesClient(config)
        self.metrics_collector = MetricsCollector(config)
        self.templates_dir = "/tmp/nodeguardian/templates"
        self._ensure_templates_dir()
        self._create_default_templates()
    
    def _ensure_templates_dir(self) -> None:
        """Ensure templates directory exists."""
        import os
        os.makedirs(self.templates_dir, exist_ok=True)
    
    def _create_default_templates(self) -> None:
        """Create default alert templates."""
        default_templates = {
            "default": {
                "subject": "[NodeGuardian] 节点告警 - {{ rule_name }}",
                "body": """节点告警触发：

规则名称: {{ rule_name }}
规则描述: {{ rule_description }}
触发时间: {{ timestamp }}

节点指标:
{% for node in triggered_nodes %}
Node: {{ node.name }}
  CPU: {{ node.metrics.cpu_utilization }}%
  Memory: {{ node.metrics.memory_utilization }}%
  Disk: {{ node.metrics.disk_utilization }}%
{% endfor %}

问题Pod:
{% for node in triggered_nodes %}
{% for pod in node.problem_pods %}
- {{ pod.name }} ({{ pod.namespace }}): {{ pod.phase }}
{% endfor %}
{% endfor %}

请及时处理。""",
                "channels": ["email", "slack", "webhook"]
            },
            "high-load-alert": {
                "subject": "[NodeGuardian] 高负载告警 - {{ rule_name }}",
                "body": """🚨 节点高负载告警

规则: {{ rule_name }}
时间: {{ timestamp }}

受影响节点:
{% for node in triggered_nodes %}
Node: {{ node.name }}
  CPU负载率: {{ node.metrics.cpu_load_ratio }}
  CPU使用率: {{ node.metrics.cpu_utilization }}%
  Memory使用率: {{ node.metrics.memory_utilization }}%
{% endfor %}

已执行动作:
- 添加污点防止新Pod调度
- 标记节点状态

请检查节点资源使用情况。""",
                "channels": ["email", "slack"]
            },
            "emergency-alert": {
                "subject": "🚨 [NodeGuardian] 紧急告警 - {{ rule_name }}",
                "body": """🚨🚨🚨 紧急告警 🚨🚨🚨

规则: {{ rule_name }}
时间: {{ timestamp }}

受影响节点:
{% for node in triggered_nodes %}
Node: {{ node.name }}
  Memory使用率: {{ node.metrics.memory_utilization }}%
{% endfor %}

已执行紧急动作:
- 驱逐部分Pod释放资源
- 添加NoExecute污点
- 发送紧急通知

请立即处理！""",
                "channels": ["email", "slack", "webhook"]
            },
            "recovery-alert": {
                "subject": "[NodeGuardian] 节点恢复 - {{ rule_name }}",
                "body": """✅ 节点状态恢复

规则: {{ rule_name }}
时间: {{ timestamp }}

恢复节点:
{% for node in triggered_nodes %}
Node: {{ node.name }}
  CPU使用率: {{ node.metrics.cpu_utilization }}%
  Memory使用率: {{ node.metrics.memory_utilization }}%
{% endfor %}

已执行恢复动作:
- 移除污点
- 清理标签
- 恢复正常调度

节点已恢复正常状态。""",
                "channels": ["email"]
            }
        }
        
        for template_name, template_data in default_templates.items():
            template_file = f"{self.templates_dir}/{template_name}.json"
            try:
                with open(template_file, 'r') as f:
                    # Template already exists, skip
                    continue
            except FileNotFoundError:
                # Create default template
                template_obj = {
                    "apiVersion": "nodeguardian.k8s.io/v1",
                    "kind": "AlertTemplate",
                    "metadata": {"name": template_name},
                    "spec": template_data
                }
                
                with open(template_file, 'w') as f:
                    json.dump(template_obj, f, indent=2, ensure_ascii=False)
                
                self.logger.info(f"Created default template: {template_name}")
    
    def load_template(self, template_name: str) -> Optional[Dict[str, Any]]:
        """Load alert template from file or CRD."""
        # Try to load from file first
        template_file = f"{self.templates_dir}/{template_name}.json"
        try:
            with open(template_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            pass
        
        # Try to load from CRD
        try:
            template_obj = self.k8s_client.custom_api.get_cluster_custom_object(
                group="nodeguardian.k8s.io",
                version="v1",
                plural="alerttemplates",
                name=template_name
            )
            return template_obj
        except Exception as e:
            self.logger.error(f"Failed to load template {template_name}: {e}")
            return None
    
    def send_alert(self, template_name: str, rule: Any, triggered_nodes: List[str], channels: List[str]) -> None:
        """Send alert using specified template and channels."""
        self.logger.info(f"Sending alert for template: {template_name}")
        
        # Load template
        template_obj = self.load_template(template_name)
        if not template_obj:
            self.logger.error(f"Template not found: {template_name}")
            return
        
        template_spec = template_obj.get("spec", {})
        subject_template = template_spec.get("subject", "NodeGuardian Alert")
        body_template = template_spec.get("body", "Alert triggered")
        template_channels = template_spec.get("channels", [])
        
        # Use template channels if no channels specified
        if not channels:
            channels = template_channels
        
        # Prepare context data
        context = self._prepare_context(rule, triggered_nodes)
        
        # Render templates
        try:
            subject = Template(subject_template).render(**context)
            body = Template(body_template).render(**context)
        except Exception as e:
            self.logger.error(f"Failed to render template {template_name}: {e}")
            return
        
        # Send to each channel
        for channel in channels:
            try:
                if channel == "email":
                    self._send_email_alert(subject, body)
                elif channel == "slack":
                    self._send_slack_alert(subject, body)
                elif channel == "webhook":
                    self._send_webhook_alert(subject, body, rule, triggered_nodes)
                else:
                    self.logger.warning(f"Unknown alert channel: {channel}")
            except Exception as e:
                self.logger.error(f"Failed to send alert via {channel}: {e}")
    
    def _prepare_context(self, rule: Any, triggered_nodes: List[str]) -> Dict[str, Any]:
        """Prepare context data for template rendering."""
        from datetime import datetime
        
        context = {
            "rule_name": rule.name,
            "rule_description": rule.metadata.get("description", ""),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "triggered_nodes": []
        }
        
        # Prepare node data
        for node_name in triggered_nodes:
            node_data = {
                "name": node_name,
                "metrics": {
                    "cpu_utilization": self.metrics_collector.get_node_metrics(node_name, "cpuUtilizationPercent"),
                    "memory_utilization": self.metrics_collector.get_node_metrics(node_name, "memoryUtilizationPercent"),
                    "disk_utilization": self.metrics_collector.get_node_metrics(node_name, "diskUtilizationPercent"),
                    "cpu_load_ratio": self.metrics_collector.get_node_metrics(node_name, "cpuLoadRatio"),
                },
                "problem_pods": []
            }
            
            # Get problem pods
            pods = self.k8s_client.get_pods_on_node(node_name)
            node_data["problem_pods"] = pods[:5]  # Limit to 5 pods
            
            context["triggered_nodes"].append(node_data)
        
        return context
    
    def _send_email_alert(self, subject: str, body: str) -> None:
        """Send email alert."""
        if not self.config.alert_email_to:
            self.logger.warning("Email alert configured but ALERT_EMAIL_TO not set")
            return
        
        self.logger.info(f"Sending email alert to: {self.config.alert_email_to}")
        
        try:
            msg = MimeMultipart()
            msg['From'] = self.config.alert_email_from
            msg['To'] = self.config.alert_email_to
            msg['Subject'] = subject
            
            msg.attach(MimeText(body, 'plain', 'utf-8'))
            
            # Parse SMTP server and port
            smtp_server, smtp_port = self.config.alert_email_smtp.split(':')
            smtp_port = int(smtp_port)
            
            # Send email
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            # Note: In production, you should use proper authentication
            server.send_message(msg)
            server.quit()
            
            self.logger.info("Email alert sent successfully")
        except Exception as e:
            self.logger.error(f"Failed to send email alert: {e}")
    
    def _send_slack_alert(self, subject: str, body: str) -> None:
        """Send Slack alert."""
        if not self.config.alert_slack_webhook:
            self.logger.warning("Slack alert configured but ALERT_SLACK_WEBHOOK not set")
            return
        
        self.logger.info("Sending Slack alert")
        
        try:
            slack_message = {
                "text": subject,
                "attachments": [
                    {
                        "color": "danger",
                        "text": body,
                        "footer": "NodeGuardian",
                        "ts": int(datetime.now().timestamp())
                    }
                ]
            }
            
            response = requests.post(
                self.config.alert_slack_webhook,
                json=slack_message,
                timeout=10
            )
            response.raise_for_status()
            
            self.logger.info("Slack alert sent successfully")
        except Exception as e:
            self.logger.error(f"Failed to send Slack alert: {e}")
    
    def _send_webhook_alert(self, subject: str, body: str, rule: Any, triggered_nodes: List[str]) -> None:
        """Send webhook alert."""
        if not self.config.alert_webhook_url:
            self.logger.warning("Webhook alert configured but ALERT_WEBHOOK_URL not set")
            return
        
        self.logger.info("Sending webhook alert")
        
        try:
            webhook_payload = {
                "alert": {
                    "subject": subject,
                    "body": body,
                    "timestamp": datetime.now().isoformat() + "Z",
                    "rule": {
                        "name": rule.name,
                        "description": rule.metadata.get("description", ""),
                        "conditions": [
                            {
                                "metric": c.metric,
                                "operator": c.operator,
                                "value": c.value,
                                "description": c.description
                            } for c in rule.conditions
                        ]
                    },
                    "triggeredNodes": triggered_nodes
                }
            }
            
            response = requests.post(
                self.config.alert_webhook_url,
                json=webhook_payload,
                timeout=10
            )
            response.raise_for_status()
            
            self.logger.info("Webhook alert sent successfully")
        except Exception as e:
            self.logger.error(f"Failed to send webhook alert: {e}")
