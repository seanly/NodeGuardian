#!/usr/bin/env python3
"""
NodeGuardian Alert Manager Python Script
处理告警模板渲染和发送
"""

import json
import os
import sys
import logging
import subprocess
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Any, Optional
from pathlib import Path

# 导入配置加载器
from config_loader import get_config, get_config_section, get_config_value

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AlertManager:
    """NodeGuardian告警管理器"""
    
    def __init__(self):
        self.config_dir = "/etc/nodeguardian/config"
        self.secrets_dir = "/etc/nodeguardian/secrets"
        self.config_file = f"{self.config_dir}/config.json"
        self.templates_dir = "/tmp/nodeguardian/templates"
        
        # 确保目录存在
        Path(self.templates_dir).mkdir(parents=True, exist_ok=True)
        
        # 加载配置
        self.config = get_config()
    
    def run(self, args: List[str]) -> None:
        """主运行函数"""
        try:
            if len(args) >= 4:
                # 直接调用模式
                template_name = args[0]
                rule_object = json.loads(args[1])
                triggered_nodes = json.loads(args[2])
                channels = json.loads(args[3])
                
                logger.info(f"Processing direct alert call: template={template_name}, nodes={triggered_nodes}")
                self.send_alert(template_name, rule_object, triggered_nodes, channels)
            else:
                # 绑定上下文模式
                binding_context_path = os.environ.get('BINDING_CONTEXT_PATH', '/tmp/binding_context.json')
                
                if not os.path.exists(binding_context_path):
                    logger.error(f"Binding context file not found: {binding_context_path}")
                    sys.exit(1)
                
                with open(binding_context_path, 'r') as f:
                    binding_context = json.load(f)
                
                if not binding_context:
                    logger.error("Empty binding context")
                    sys.exit(1)
                
                # 处理绑定上下文
                context_type = binding_context[0].get('type')
                binding = binding_context[0].get('binding')
                
                logger.info(f"Alert manager processing: type={context_type}, binding={binding}")
                
                if context_type == "Synchronization":
                    self.handle_templates_synchronization(binding_context[0])
                elif context_type == "Event":
                    self.handle_template_event(binding_context[0])
                else:
                    logger.warning(f"Unknown binding context type: {context_type}")
                    
        except Exception as e:
            logger.error(f"Error in main run: {e}")
            sys.exit(1)
    
    def handle_templates_synchronization(self, context: Dict[str, Any]) -> None:
        """处理模板同步"""
        objects = context.get('objects', [])
        logger.info(f"Synchronizing {len(objects)} AlertTemplate objects")
        
        for obj in objects:
            template_object = obj.get('object', {})
            self.register_alert_template(template_object)
    
    def handle_template_event(self, context: Dict[str, Any]) -> None:
        """处理模板事件"""
        watch_event = context.get('watchEvent')
        template_object = context.get('object', {})
        template_name = template_object.get('metadata', {}).get('name')
        
        logger.info(f"Processing template event: {watch_event} for template: {template_name}")
        
        if watch_event in ["Added", "Modified"]:
            self.register_alert_template(template_object)
        elif watch_event == "Deleted":
            self.unregister_alert_template(template_name)
    
    def register_alert_template(self, template_object: Dict[str, Any]) -> None:
        """注册告警模板"""
        template_name = template_object.get('metadata', {}).get('name')
        logger.info(f"Registering alert template: {template_name}")
        
        # 保存模板到文件
        template_file = f"{self.templates_dir}/{template_name}.json"
        with open(template_file, 'w') as f:
            json.dump(template_object, f, indent=2)
        
        logger.info(f"Alert template registered: {template_name}")
    
    def unregister_alert_template(self, template_name: str) -> None:
        """注销告警模板"""
        logger.info(f"Unregistering alert template: {template_name}")
        
        # 删除模板文件
        template_file = f"{self.templates_dir}/{template_name}.json"
        if os.path.exists(template_file):
            os.remove(template_file)
        
        logger.info(f"Alert template unregistered: {template_name}")
    
    def send_alert(self, template_name: str, rule_object: Dict[str, Any], triggered_nodes: List[str], channels: List[Dict[str, Any]]) -> None:
        """发送告警"""
        # 获取模板
        template_file = f"{self.templates_dir}/{template_name}.json"
        if not os.path.exists(template_file):
            logger.warning(f"Alert template not found: {template_name}, using default")
            self.create_default_template(template_name)
        
        with open(template_file, 'r') as f:
            template_object = json.load(f)
        
        # 渲染告警内容
        alert_content = self.render_alert_content(template_object, rule_object, triggered_nodes)
        
        # 发送到各个渠道
        self.send_to_channels(alert_content, channels, template_object)
    
    def create_default_template(self, template_name: str) -> None:
        """创建默认模板"""
        template_file = f"{self.templates_dir}/{template_name}.json"
        
        default_template = {
            "metadata": {
                "name": template_name
            },
            "spec": {
                "title": "NodeGuardian Alert",
                "summary": "NodeGuardian rule triggered",
                "description": "Rule {{.ruleName}} has been triggered on nodes: {{.triggeredNodes}}",
                "severity": "warning",
                "channels": [
                    {
                        "type": "log",
                        "enabled": True
                    }
                ]
            }
        }
        
        with open(template_file, 'w') as f:
            json.dump(default_template, f, indent=2)
    
    def render_alert_content(self, template_object: Dict[str, Any], rule_object: Dict[str, Any], triggered_nodes: List[str]) -> Dict[str, Any]:
        """渲染告警内容"""
        # 检查是否是恢复告警
        alert_type = rule_object.get('type', 'trigger')
        
        rule_name = rule_object.get('metadata', {}).get('name', 'unknown')
        rule_description = rule_object.get('spec', {}).get('metadata', {}).get('description', 'No description')
        rule_severity = rule_object.get('spec', {}).get('metadata', {}).get('severity', 'warning')
        
        # 获取模板字段
        spec = template_object.get('spec', {})
        title = spec.get('title', 'NodeGuardian Alert')
        summary = spec.get('summary', 'Rule triggered')
        description = spec.get('description', 'Rule {{.ruleName}} triggered')
        severity = spec.get('severity', 'warning')
        
        # 如果是恢复告警，使用恢复相关的默认值
        if alert_type == "recovery":
            title = spec.get('title', 'NodeGuardian Recovery Alert')
            summary = spec.get('summary', 'Node recovered')
            description = spec.get('description', 'Node {{.triggeredNodes}} has recovered from rule {{.ruleName}}')
            severity = spec.get('severity', 'info')
        
        # 简单的模板替换
        rendered_title = title.replace('{{.ruleName}}', rule_name)
        rendered_summary = summary.replace('{{.ruleName}}', rule_name)
        rendered_description = description.replace('{{.ruleName}}', rule_name).replace('{{.triggeredNodes}}', ', '.join(triggered_nodes))
        
        # 构建告警内容
        alert_content = {
            "title": rendered_title,
            "summary": rendered_summary,
            "description": rendered_description,
            "severity": severity,
            "ruleName": rule_name,
            "ruleDescription": rule_description,
            "triggeredNodes": triggered_nodes,
            "timestamp": self.get_current_timestamp()
        }
        
        return alert_content
    
    def send_to_channels(self, alert_content: Dict[str, Any], channels: List[Dict[str, Any]], template_object: Dict[str, Any]) -> None:
        """发送到各个渠道"""
        # 获取模板中的默认渠道
        template_channels = template_object.get('spec', {}).get('channels', [])
        
        # 合并渠道
        all_channels = channels + template_channels
        # 去重
        unique_channels = []
        seen = set()
        for channel in all_channels:
            channel_key = json.dumps(channel, sort_keys=True)
            if channel_key not in seen:
                unique_channels.append(channel)
                seen.add(channel_key)
        
        for channel in unique_channels:
            channel_type = channel.get('type')
            channel_enabled = channel.get('enabled', True)
            
            if channel_enabled:
                self.send_to_channel(channel_type, channel, alert_content)
    
    def send_to_channel(self, channel_type: str, channel_config: Dict[str, Any], alert_content: Dict[str, Any]) -> None:
        """发送到单个渠道"""
        if channel_type == "log":
            self.send_to_log(alert_content)
        elif channel_type == "webhook":
            self.send_to_webhook(channel_config, alert_content)
        elif channel_type == "email":
            self.send_to_email(channel_config, alert_content)
        else:
            logger.warning(f"Unknown channel type: {channel_type}")
    
    def send_to_log(self, alert_content: Dict[str, Any]) -> None:
        """发送到日志"""
        title = alert_content.get('title')
        summary = alert_content.get('summary')
        severity = alert_content.get('severity')
        rule_name = alert_content.get('ruleName')
        triggered_nodes = alert_content.get('triggeredNodes')
        
        logger.info(f"ALERT [{severity}] {title} - {summary}")
        logger.info(f"Rule: {rule_name}, Nodes: {triggered_nodes}")
    
    def send_to_webhook(self, channel_config: Dict[str, Any], alert_content: Dict[str, Any]) -> None:
        """发送到Webhook"""
        webhook_url = None
        webhook_headers = {}
        
        if channel_config and channel_config != {}:
            # 使用传入的配置
            webhook_url = channel_config.get('url')
            webhook_headers = channel_config.get('headers', {})
        else:
            # 使用ConfigMap中的配置
            webhook_url = self.config.get('alert', {}).get('webhookUrl')
        
        if not webhook_url:
            logger.warning("Webhook URL not configured")
            return
        
        logger.info(f"Sending alert to webhook: {webhook_url}")
        
        try:
            # 设置默认headers
            headers = {
                'Content-Type': 'application/json'
            }
            headers.update(webhook_headers)
            
            # 发送请求
            response = requests.post(
                webhook_url,
                json=alert_content,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            logger.info("Webhook alert sent successfully")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send webhook alert: {e}")
    
    def send_to_email(self, channel_config: Dict[str, Any], alert_content: Dict[str, Any]) -> None:
        """发送到邮件"""
        try:
            # 获取邮件配置
            email_config = self.config.get('email', {})
            
            # 加载敏感信息
            from config_loader import config_loader
            username = config_loader.load_secret('email-username')
            password = config_loader.load_secret('email-password')
            
            if not username or not password:
                logger.error("Email credentials not configured")
                return
            
            smtp_server = email_config.get('smtpServer', 'smtp.gmail.com')
            smtp_port = email_config.get('smtpPort', 587)
            use_tls = email_config.get('useTLS', True)
            use_ssl = email_config.get('useSSL', False)
            from_addr = email_config.get('from', 'nodeguardian@example.com')
            to_addrs = email_config.get('to', ['admin@example.com'])
            
            # 创建邮件内容
            msg = MIMEMultipart('alternative')
            msg['From'] = from_addr
            msg['To'] = ', '.join(to_addrs)
            msg['Subject'] = f"[{alert_content.get('severity', 'INFO').upper()}] {alert_content.get('title', 'NodeGuardian Alert')}"
            
            # 创建HTML内容
            html_content = self.create_email_html(alert_content)
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # 发送邮件
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)
                if use_tls:
                    server.starttls()
            
            server.login(username, password)
            server.send_message(msg)
            server.quit()
            
            logger.info("Email sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
    
    def create_email_html(self, alert_content: Dict[str, Any]) -> str:
        """创建邮件HTML内容"""
        severity = alert_content.get('severity', 'info')
        severity_colors = {
            'critical': '#dc3545',
            'warning': '#ffc107',
            'info': '#17a2b8',
            'success': '#28a745'
        }
        color = severity_colors.get(severity, '#6c757d')
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>NodeGuardian Alert</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: {color}; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">{alert_content.get('title', 'NodeGuardian Alert')}</h1>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                    <h2 style="margin-top: 0; color: #495057;">Summary</h2>
                    <p>{alert_content.get('summary', '')}</p>
                </div>
                
                <div style="background-color: #ffffff; padding: 15px; border: 1px solid #dee2e6; border-radius: 5px; margin-bottom: 20px;">
                    <h3 style="margin-top: 0; color: #495057;">Details</h3>
                    <p><strong>Rule:</strong> {alert_content.get('ruleName', 'Unknown')}</p>
                    <p><strong>Description:</strong> {alert_content.get('ruleDescription', 'No description')}</p>
                    <p><strong>Triggered Nodes:</strong> {', '.join(alert_content.get('triggeredNodes', []))}</p>
                    <p><strong>Timestamp:</strong> {alert_content.get('timestamp', '')}</p>
                </div>
                
                <div style="background-color: #e9ecef; padding: 15px; border-radius: 5px;">
                    <h3 style="margin-top: 0; color: #495057;">Full Description</h3>
                    <p>{alert_content.get('description', '')}</p>
                </div>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 12px;">
                    <p>This alert was generated by NodeGuardian</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"

def main():
    """主函数"""
    alert_manager = AlertManager()
    alert_manager.run(sys.argv[1:])

if __name__ == "__main__":
    main()
