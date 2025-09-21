#!/usr/bin/env python3
"""
NodeGuardian Configuration Loader
统一配置加载模块，支持从ConfigMap和Secret加载配置
"""

import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigLoader:
    """配置加载器"""
    
    def __init__(self):
        self.config_dir = "/etc/nodeguardian/config"
        self.secrets_dir = "/etc/nodeguardian/secrets"
        self.config_file = f"{self.config_dir}/config.json"
        self._config_cache = None
    
    def load_config(self) -> Dict[str, Any]:
        """加载统一配置文件"""
        if self._config_cache is not None:
            return self._config_cache
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
            else:
                # 返回默认配置
                config = self.get_default_config()
            
            # 加载敏感信息
            config = self.load_secrets(config)
            
            self._config_cache = config
            return config
            
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "email": {
                "smtpServer": "smtp.gmail.com",
                "smtpPort": 587,
                "username": "",
                "password": "",
                "from": "nodeguardian@example.com",
                "to": ["admin@example.com"],
                "useTLS": True,
                "useSSL": False
            },
            "prometheus": {
                "url": "http://prometheus-k8s.monitoring.svc:9090",
                "timeout": "30s",
                "retries": 3,
                "queryTimeout": "60s",
                "maxSamples": 10000
            },
            "alert": {
                "webhookUrl": "",
                "defaultChannels": ["log", "email"],
                "retryAttempts": 3,
                "retryDelay": "5s",
                "batchSize": 10,
                "batchTimeout": "30s"
            },
            "monitoring": {
                "defaultCheckInterval": "30s",
                "defaultCooldownPeriod": "10m",
                "metricsServerUrl": "https://kubernetes.default.svc:443/apis/metrics.k8s.io/v1beta1",
                "maxConcurrentChecks": 10,
                "healthCheckInterval": "60s"
            },
            "log": {
                "level": "INFO",
                "format": "json",
                "output": "stdout",
                "maxSize": "100MB",
                "maxBackups": 3,
                "maxAge": "7d"
            },
            "node": {
                "defaultTaintKey": "nodeguardian.io/status",
                "defaultTaintEffect": "NoSchedule",
                "defaultLabelPrefix": "nodeguardian.io/",
                "excludeNamespaces": ["kube-system", "kube-public", "monitoring"],
                "maxEvictionPods": 10
            },
            "python": {
                "enabled": True,
                "scriptsPath": "/scripts",
                "logLevel": "INFO",
                "timeout": "300s",
                "maxRetries": 3
            }
        }
    
    def load_secrets(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """加载Secret配置"""
        try:
            # 加载邮件凭据
            email_username = self.load_secret("email-username")
            email_password = self.load_secret("email-password")
            
            if email_username:
                config["email"]["username"] = email_username
            if email_password:
                config["email"]["password"] = email_password
            
            # 加载webhook URL
            webhook_url = self.load_secret("webhook-url")
            if webhook_url:
                config["alert"]["webhookUrl"] = webhook_url
            
            return config
            
        except Exception as e:
            logger.error(f"Failed to load secrets: {e}")
            return config
    
    def load_secret(self, secret_name: str) -> str:
        """加载单个Secret"""
        try:
            secret_file = f"{self.secrets_dir}/{secret_name}"
            if os.path.exists(secret_file):
                with open(secret_file, 'r') as f:
                    return f.read().strip()
            return ""
        except Exception as e:
            logger.error(f"Failed to load secret {secret_name}: {e}")
            return ""
    
    def get_config_section(self, section: str) -> Dict[str, Any]:
        """获取配置的特定部分"""
        config = self.load_config()
        return config.get(section, {})
    
    def get_config_value(self, section: str, key: str, default: Any = None) -> Any:
        """获取配置值"""
        section_config = self.get_config_section(section)
        return section_config.get(key, default)
    
    def reload_config(self) -> Dict[str, Any]:
        """重新加载配置"""
        self._config_cache = None
        return self.load_config()

# 全局配置加载器实例
config_loader = ConfigLoader()

def get_config() -> Dict[str, Any]:
    """获取配置"""
    return config_loader.load_config()

def get_config_section(section: str) -> Dict[str, Any]:
    """获取配置的特定部分"""
    return config_loader.get_config_section(section)

def get_config_value(section: str, key: str, default: Any = None) -> Any:
    """获取配置值"""
    return config_loader.get_config_value(section, key, default)

def reload_config() -> Dict[str, Any]:
    """重新加载配置"""
    return config_loader.reload_config()
