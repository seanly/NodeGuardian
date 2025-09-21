#!/usr/bin/env python3
"""
NodeGuardian Configuration Manager
统一配置管理工具
"""

import json
import argparse
import sys
import os
from typing import Dict, Any, Optional

class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.config_template = {
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
            }
        }
    
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return self.config_template.copy()
    
    def save_config(self, config: Dict[str, Any], config_file: str) -> None:
        """保存配置文件"""
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def update_config(self, config: Dict[str, Any], section: str, key: str, value: Any) -> None:
        """更新配置项"""
        if section not in config:
            config[section] = {}
        
        # 处理嵌套键 (如 "email.username")
        if '.' in key:
            keys = key.split('.')
            current = config[section]
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            current[keys[-1]] = value
        else:
            config[section][key] = value
    
    def get_config(self, config: Dict[str, Any], section: str, key: str, default: Any = None) -> Any:
        """获取配置项"""
        if section not in config:
            return default
        
        # 处理嵌套键
        if '.' in key:
            keys = key.split('.')
            current = config[section]
            for k in keys:
                if k not in current:
                    return default
                current = current[k]
            return current
        else:
            return config[section].get(key, default)
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """验证配置"""
        errors = []
        
        # 验证邮件配置
        if 'email' in config:
            email_config = config['email']
            if not email_config.get('smtpServer'):
                errors.append("Email SMTP server is required")
            if not email_config.get('from'):
                errors.append("Email from address is required")
            if not email_config.get('to'):
                errors.append("Email to addresses are required")
        
        # 验证Prometheus配置
        if 'prometheus' in config:
            prometheus_config = config['prometheus']
            if not prometheus_config.get('url'):
                errors.append("Prometheus URL is required")
        
        # 验证监控配置
        if 'monitoring' in config:
            monitoring_config = config['monitoring']
            if not monitoring_config.get('defaultCheckInterval'):
                errors.append("Default check interval is required")
            if not monitoring_config.get('defaultCooldownPeriod'):
                errors.append("Default cooldown period is required")
        
        if errors:
            print("Configuration validation errors:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        return True
    
    def generate_k8s_configmap(self, config: Dict[str, Any]) -> str:
        """生成Kubernetes ConfigMap YAML"""
        config_json = json.dumps(config, indent=2, ensure_ascii=False)
        
        yaml_content = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: nodeguardian-config
  namespace: nodeguardian-system
  labels:
    app: nodeguardian
    component: config
data:
  config.json: |
{self._indent_yaml(config_json, 4)}
"""
        return yaml_content
    
    def generate_k8s_secret(self, secrets: Dict[str, str]) -> str:
        """生成Kubernetes Secret YAML"""
        yaml_content = """apiVersion: v1
kind: Secret
metadata:
  name: nodeguardian-secrets
  namespace: nodeguardian-system
  labels:
    app: nodeguardian
    component: secrets
type: Opaque
data:
"""
        
        for key, value in secrets.items():
            yaml_content += f"  {key}: {value}\n"
        
        return yaml_content
    
    def _indent_yaml(self, text: str, indent: int) -> str:
        """为YAML内容添加缩进"""
        lines = text.split('\n')
        indented_lines = []
        for line in lines:
            if line.strip():
                indented_lines.append(' ' * indent + line)
            else:
                indented_lines.append('')
        return '\n'.join(indented_lines)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='NodeGuardian Configuration Manager')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # 初始化命令
    init_parser = subparsers.add_parser('init', help='Initialize configuration file')
    init_parser.add_argument('--output', '-o', default='config.json', help='Output config file')
    
    # 更新命令
    update_parser = subparsers.add_parser('update', help='Update configuration')
    update_parser.add_argument('--config', '-c', default='config.json', help='Config file')
    update_parser.add_argument('--section', '-s', required=True, help='Configuration section')
    update_parser.add_argument('--key', '-k', required=True, help='Configuration key')
    update_parser.add_argument('--value', '-v', required=True, help='Configuration value')
    
    # 获取命令
    get_parser = subparsers.add_parser('get', help='Get configuration value')
    get_parser.add_argument('--config', '-c', default='config.json', help='Config file')
    get_parser.add_argument('--section', '-s', required=True, help='Configuration section')
    get_parser.add_argument('--key', '-k', required=True, help='Configuration key')
    
    # 验证命令
    validate_parser = subparsers.add_parser('validate', help='Validate configuration')
    validate_parser.add_argument('--config', '-c', default='config.json', help='Config file')
    
    # 生成K8s资源命令
    k8s_parser = subparsers.add_parser('k8s', help='Generate Kubernetes resources')
    k8s_parser.add_argument('--config', '-c', default='config.json', help='Config file')
    k8s_parser.add_argument('--output', '-o', default='k8s-resources.yaml', help='Output file')
    k8s_parser.add_argument('--secrets', help='Secrets file (JSON format)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    manager = ConfigManager()
    
    try:
        if args.command == 'init':
            config = manager.config_template.copy()
            manager.save_config(config, args.output)
            print(f"Configuration file initialized: {args.output}")
            
        elif args.command == 'update':
            config = manager.load_config(args.config)
            manager.update_config(config, args.section, args.key, args.value)
            manager.save_config(config, args.config)
            print(f"Configuration updated: {args.section}.{args.key} = {args.value}")
            
        elif args.command == 'get':
            config = manager.load_config(args.config)
            value = manager.get_config(config, args.section, args.key)
            print(value)
            
        elif args.command == 'validate':
            config = manager.load_config(args.config)
            if manager.validate_config(config):
                print("Configuration is valid")
                sys.exit(0)
            else:
                sys.exit(1)
                
        elif args.command == 'k8s':
            config = manager.load_config(args.config)
            
            # 生成ConfigMap
            configmap_yaml = manager.generate_k8s_configmap(config)
            
            # 生成Secret（如果提供了secrets文件）
            secret_yaml = ""
            if args.secrets and os.path.exists(args.secrets):
                with open(args.secrets, 'r', encoding='utf-8') as f:
                    secrets = json.load(f)
                secret_yaml = "\n---\n" + manager.generate_k8s_secret(secrets)
            
            # 保存到文件
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(configmap_yaml)
                f.write(secret_yaml)
            
            print(f"Kubernetes resources generated: {args.output}")
            
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
