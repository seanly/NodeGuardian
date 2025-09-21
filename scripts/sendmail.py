#!/usr/bin/env python3
"""
NodeGuardian Email Sender
邮件发送脚本，支持SMTP邮件发送功能
"""

import sys
import json
import smtplib
import argparse
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置路径
CONFIG_DIR = "/etc/nodeguardian/config"
SECRETS_DIR = "/etc/nodeguardian/secrets"
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_unified_config() -> Dict[str, Any]:
    """加载统一配置文件"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.warning("Failed to load unified config: %s", str(e))
    
    # 返回默认配置
    return {
        "email": {
            "smtpServer": "smtp.gmail.com",
            "smtpPort": 587,
            "useTLS": True,
            "useSSL": False
        }
    }


def load_secret(secret_name: str) -> Optional[str]:
    """加载Secret配置"""
    secret_file = os.path.join(SECRETS_DIR, secret_name)
    if os.path.exists(secret_file):
        try:
            with open(secret_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except (IOError, OSError) as e:
            logger.warning("Failed to load secret %s: %s", secret_name, str(e))
    return None


def merge_config_with_secrets(config: Dict[str, Any]) -> Dict[str, Any]:
    """合并配置和Secret"""
    # 加载Secret中的敏感信息
    email_username = load_secret("email-username")
    email_password = load_secret("email-password")
    
    # 合并到配置中
    if email_username:
        config["email"]["username"] = email_username
    
    if email_password:
        config["email"]["password"] = email_password
    
    return config


class EmailSender:
    """邮件发送器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化邮件发送器
        
        Args:
            config: 邮件配置字典
        """
        self.smtp_server = config.get('smtpServer', 'smtp.gmail.com')
        self.smtp_port = int(config.get('smtpPort', 587))
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        self.from_email = config.get('from', '')
        self.to_emails = config.get('to', [])
        self.use_tls = config.get('useTLS', True)
        self.use_ssl = config.get('useSSL', False)
        
        # 确保to_emails是列表
        if isinstance(self.to_emails, str):
            self.to_emails = [self.to_emails]
    
    def validate_config(self) -> bool:
        """
        验证邮件配置
        
        Returns:
            bool: 配置是否有效
        """
        if not self.smtp_server:
            logger.error("SMTP server not configured")
            return False
        
        if not self.from_email:
            logger.error("From email not configured")
            return False
        
        if not self.to_emails:
            logger.error("To emails not configured")
            return False
        
        return True
    
    def create_message(self, subject: str, body: str, is_html: bool = False) -> MIMEMultipart:
        """
        创建邮件消息
        
        Args:
            subject: 邮件主题
            body: 邮件正文
            is_html: 是否为HTML格式
            
        Returns:
            MIMEMultipart: 邮件消息对象
        """
        msg = MIMEMultipart('alternative')
        msg['From'] = self.from_email
        msg['To'] = ', '.join(self.to_emails)
        msg['Subject'] = subject
        
        # 添加邮件正文
        if is_html:
            msg.attach(MIMEText(body, 'html', 'utf-8'))
        else:
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        return msg
    
    def send_email(self, subject: str, body: str, is_html: bool = False) -> bool:
        """
        发送邮件
        
        Args:
            subject: 邮件主题
            body: 邮件正文
            is_html: 是否为HTML格式
            
        Returns:
            bool: 发送是否成功
        """
        if not self.validate_config():
            return False
        
        try:
            # 创建邮件消息
            msg = self.create_message(subject, body, is_html)
            
            # 连接SMTP服务器
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                if self.use_tls:
                    server.starttls()
            
            # 登录
            if self.username and self.password:
                server.login(self.username, self.password)
            
            # 发送邮件
            text = msg.as_string()
            server.sendmail(self.from_email, self.to_emails, text)
            server.quit()
            
            logger.info("Email sent successfully to %s", ', '.join(self.to_emails))
            return True
            
        except (smtplib.SMTPException, ConnectionError, OSError) as e:
            logger.error("Failed to send email: %s", str(e))
            return False


def format_alert_email(alert_data: Dict[str, Any]) -> tuple[str, str]:
    """
    格式化告警邮件内容
    
    Args:
        alert_data: 告警数据
        
    Returns:
        tuple: (subject, body) 邮件主题和正文
    """
    title = alert_data.get('title', 'NodeGuardian Alert')
    summary = alert_data.get('summary', '')
    severity = alert_data.get('severity', 'info')
    rule_name = alert_data.get('ruleName', '')
    triggered_nodes = alert_data.get('triggeredNodes', '')
    description = alert_data.get('description', '')
    timestamp = alert_data.get('timestamp', '')
    
    # 根据严重程度设置主题前缀
    severity_prefix = {
        'critical': '[CRITICAL]',
        'error': '[ERROR]',
        'warning': '[WARNING]',
        'info': '[INFO]'
    }.get(severity.lower(), '[INFO]')
    
    subject = f"{severity_prefix} {title}"
    
    # 创建HTML格式的邮件正文
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .header {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .alert-box {{ border-left: 4px solid {'#dc3545' if severity.lower() in ['critical', 'error'] else '#ffc107' if severity.lower() == 'warning' else '#28a745'}; padding: 15px; margin: 10px 0; background-color: #f8f9fa; }}
            .info-table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
            .info-table th, .info-table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            .info-table th {{ background-color: #f2f2f2; }}
            .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>{title}</h2>
        </div>
        
        <div class="alert-box">
            <h3>告警摘要</h3>
            <p>{summary}</p>
        </div>
        
        <table class="info-table">
            <tr>
                <th>严重程度</th>
                <td><strong>{severity.upper()}</strong></td>
            </tr>
            <tr>
                <th>规则名称</th>
                <td>{rule_name}</td>
            </tr>
            <tr>
                <th>触发节点</th>
                <td>{triggered_nodes}</td>
            </tr>
            <tr>
                <th>时间戳</th>
                <td>{timestamp}</td>
            </tr>
        </table>
        
        {f'<div class="alert-box"><h3>详细描述</h3><p>{description}</p></div>' if description else ''}
        
        <div class="footer">
            <p>此邮件由 NodeGuardian 自动发送</p>
            <p>请及时处理相关告警</p>
        </div>
    </body>
    </html>
    """
    
    return subject, html_body


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='NodeGuardian Email Sender')
    parser.add_argument('--config', help='Email configuration JSON string (optional, overrides unified config)')
    parser.add_argument('--alert-data', required=True, help='Alert data JSON string')
    parser.add_argument('--format', choices=['html', 'text'], default='html', help='Email format')
    
    args = parser.parse_args()
    
    try:
        # 解析告警数据
        alert_data = json.loads(args.alert_data)
        
        # 获取邮件配置
        if args.config:
            # 使用传入的配置（覆盖统一配置）
            logger.info("Using provided configuration")
            email_config = json.loads(args.config)
        else:
            # 默认使用统一配置
            logger.info("Loading configuration from unified config")
            full_config = load_unified_config()
            config = merge_config_with_secrets(full_config)
            email_config = config.get("email", {})
        
        # 创建邮件发送器
        email_sender = EmailSender(email_config)
        
        # 格式化邮件内容
        subject, body = format_alert_email(alert_data)
        
        # 发送邮件
        is_html = args.format == 'html'
        success = email_sender.send_email(subject, body, is_html)
        
        if success:
            print("Email sent successfully")
            sys.exit(0)
        else:
            print("Failed to send email")
            sys.exit(1)
            
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON: %s", str(e))
        sys.exit(1)
    except (ValueError, KeyError, TypeError) as e:
        logger.error("Unexpected error: %s", str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
