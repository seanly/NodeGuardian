#!/usr/bin/env python3
"""
NodeGuardian Recovery Manager Python Script
处理节点恢复逻辑和恢复动作执行
"""

import json
import os
import sys
import logging
import subprocess
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

class RecoveryManager:
    """NodeGuardian恢复管理器"""
    
    def __init__(self):
        self.config_dir = "/etc/nodeguardian/config"
        self.secrets_dir = "/etc/nodeguardian/secrets"
        self.config_file = f"{self.config_dir}/config.json"
        self.rules_dir = "/tmp/nodeguardian/rules"
        self.cooldown_dir = "/tmp/nodeguardian/cooldown"
        
        # 确保目录存在
        Path(self.rules_dir).mkdir(parents=True, exist_ok=True)
        Path(self.cooldown_dir).mkdir(parents=True, exist_ok=True)
        
        # 加载配置
        self.config = get_config()
    
    def run(self, args: List[str]) -> None:
        """主运行函数"""
        try:
            # 读取绑定上下文
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
            
            logger.info(f"Recovery manager processing: type={context_type}, binding={binding}")
            
            if context_type == "Schedule" and binding == "recovery-check":
                self.check_recovery_conditions()
            else:
                logger.warning(f"Unknown binding context type: {context_type}")
                
        except Exception as e:
            logger.error(f"Error in main run: {e}")
            sys.exit(1)
    
    def check_recovery_conditions(self) -> None:
        """检查恢复条件"""
        logger.debug("Checking recovery conditions for all rules...")
        
        if not os.path.exists(self.rules_dir):
            return
        
        for rule_file in Path(self.rules_dir).glob("*.json"):
            if rule_file.is_file():
                rule_name = rule_file.stem
                self.check_rule_recovery(str(rule_file))
    
    def check_rule_recovery(self, rule_file: str) -> None:
        """检查单个规则的恢复条件"""
        try:
            with open(rule_file, 'r') as f:
                rule_object = json.load(f)
            
            rule_name = rule_object.get('metadata', {}).get('name')
            rule_enabled = rule_object.get('spec', {}).get('metadata', {}).get('enabled', True)
            
            if not rule_enabled:
                return
            
            # 检查是否有恢复条件
            recovery_conditions = rule_object.get('spec', {}).get('recoveryConditions', [])
            if not recovery_conditions:
                return
            
            logger.debug(f"Checking recovery conditions for rule: {rule_name}")
            
            # 获取节点选择器
            node_selector = rule_object.get('spec', {}).get('nodeSelector', {})
            matching_nodes = self.get_matching_nodes(node_selector)
            
            if not matching_nodes:
                return
            
            # 检查每个节点的恢复条件
            for node_name in matching_nodes:
                if self.check_node_recovery(rule_object, node_name):
                    self.execute_recovery_actions(rule_object, node_name)
                    
        except Exception as e:
            logger.error(f"Error checking rule recovery {rule_file}: {e}")
    
    def check_node_recovery(self, rule_object: Dict[str, Any], node_name: str) -> bool:
        """检查节点的恢复条件"""
        rule_name = rule_object.get('metadata', {}).get('name')
        
        # 检查节点是否在触发状态
        if not self.is_node_triggered(rule_name, node_name):
            return False
        
        # 检查恢复冷却期
        recovery_cooldown = rule_object.get('spec', {}).get('monitoring', {}).get('recoveryCooldownPeriod', '2m')
        if self.check_cooldown(f"{rule_name}_recovery", node_name, recovery_cooldown):
            logger.debug(f"Node {node_name} is in recovery cooldown period for rule {rule_name}")
            return False
        
        # 获取恢复条件
        recovery_conditions = rule_object.get('spec', {}).get('recoveryConditions', [])
        condition_logic = rule_object.get('spec', {}).get('recoveryConditionLogic', 'AND')
        
        satisfied_conditions = 0
        
        # 评估每个恢复条件
        for condition in recovery_conditions:
            metric = condition.get('metric')
            operator = condition.get('operator')
            threshold = condition.get('value')
            duration = condition.get('duration', '5m')
            
            # 获取指标值
            metric_value = self.get_metric_value(metric, node_name)
            if metric_value is None:
                logger.error(f"Failed to get metric value for {metric} on node {node_name}")
                continue
            
            # 评估恢复条件
            if self.evaluate_condition(metric_value, operator, threshold):
                satisfied_conditions += 1
                logger.debug(f"Recovery condition satisfied for node {node_name}: {metric} {operator} {threshold} (value: {metric_value})")
            else:
                logger.debug(f"Recovery condition not satisfied for node {node_name}: {metric} {operator} {threshold} (value: {metric_value})")
        
        # 根据逻辑判断是否满足恢复条件
        if condition_logic == "AND":
            return satisfied_conditions == len(recovery_conditions)
        else:  # OR
            return satisfied_conditions > 0
    
    def is_node_triggered(self, rule_name: str, node_name: str) -> bool:
        """检查节点是否在触发状态"""
        try:
            # 检查是否有污点
            taint_key = "nodeguardian/rule-triggered"
            cmd = ["kubectl", "describe", "node", node_name]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if taint_key in result.stdout:
                return True
            
            # 检查是否有相关标签
            cmd = ["kubectl", "get", "node", node_name, "-o", "jsonpath={.metadata.labels}"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if "nodeguardian.io/rule-triggered" in result.stdout:
                return True
            
            return False
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to check if node {node_name} is triggered: {e}")
            return False
    
    def execute_recovery_actions(self, rule_object: Dict[str, Any], node_name: str) -> None:
        """执行恢复动作"""
        rule_name = rule_object.get('metadata', {}).get('name')
        
        logger.info(f"Executing recovery actions for rule: {rule_name} on node: {node_name}")
        
        # 获取恢复动作
        recovery_actions = rule_object.get('spec', {}).get('recoveryActions', [])
        
        if not recovery_actions:
            logger.info(f"No recovery actions defined for rule: {rule_name}")
            return
        
        # 执行每个恢复动作
        for action in recovery_actions:
            action_type = action.get('type')
            
            if action_type == "untaint":
                self.execute_untaint_action(action, node_name)
            elif action_type == "removeLabel":
                self.execute_remove_label_action(action, node_name)
            elif action_type == "removeAnnotation":
                self.execute_remove_annotation_action(action, node_name)
            elif action_type == "alert":
                self.execute_recovery_alert_action(action, rule_object, node_name)
            else:
                logger.warning(f"Unknown recovery action type: {action_type}")
        
        # 设置恢复冷却期
        recovery_cooldown = rule_object.get('spec', {}).get('monitoring', {}).get('recoveryCooldownPeriod', '2m')
        self.set_cooldown(f"{rule_name}_recovery", node_name)
        
        # 更新规则状态
        self.update_rule_recovery_status(rule_name, node_name)
        
        logger.info(f"Recovery actions completed for rule: {rule_name} on node: {node_name}")
    
    def execute_untaint_action(self, action: Dict[str, Any], node_name: str) -> None:
        """执行去污点动作"""
        taint_key = action.get('untaint', {}).get('key', 'nodeguardian/rule-triggered')
        taint_value = action.get('untaint', {}).get('value', 'true')
        taint_effect = action.get('untaint', {}).get('effect', 'NoSchedule')
        
        logger.info(f"Removing taint from node {node_name}: {taint_key}={taint_value}:{taint_effect}")
        
        try:
            cmd = ["kubectl", "taint", "nodes", node_name, f"{taint_key}={taint_value}:{taint_effect}", "--overwrite"]
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to remove taint from node {node_name}: {e}")
    
    def execute_remove_label_action(self, action: Dict[str, Any], node_name: str) -> None:
        """执行移除标签动作"""
        labels = action.get('removeLabel', {}).get('labels', [])
        
        for label in labels:
            logger.info(f"Removing label from node {node_name}: {label}")
            try:
                cmd = ["kubectl", "label", "nodes", node_name, f"{label}-"]
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to remove label {label} from node {node_name}: {e}")
    
    def execute_remove_annotation_action(self, action: Dict[str, Any], node_name: str) -> None:
        """执行移除注解动作"""
        annotations = action.get('removeAnnotation', {}).get('annotations', [])
        
        for annotation in annotations:
            logger.info(f"Removing annotation from node {node_name}: {annotation}")
            try:
                cmd = ["kubectl", "annotate", "nodes", node_name, f"{annotation}-"]
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to remove annotation {annotation} from node {node_name}: {e}")
    
    def execute_recovery_alert_action(self, action: Dict[str, Any], rule_object: Dict[str, Any], node_name: str) -> None:
        """执行恢复告警动作"""
        alert_enabled = action.get('alert', {}).get('enabled', True)
        if not alert_enabled:
            return
        
        template_name = action.get('alert', {}).get('template', 'recovery')
        channels = action.get('alert', {}).get('channels', [])
        
        # 为规则对象添加恢复告警信息
        recovery_rule_object = rule_object.copy()
        recovery_rule_object.update({
            "type": "recovery",
            "recoveryInfo": {
                "nodeName": node_name,
                "timestamp": self.get_current_timestamp(),
                "message": f"Node {node_name} has recovered from rule {rule_object.get('metadata', {}).get('name')}"
            }
        })
        
        # 调用告警管理器
        try:
            cmd = [
                "python3", "/scripts/alert_manager.py",
                template_name,
                json.dumps(recovery_rule_object),
                json.dumps([node_name]),
                json.dumps(channels)
            ]
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to send recovery alert: {e}")
    
    def update_rule_recovery_status(self, rule_name: str, node_name: str) -> None:
        """更新规则恢复状态"""
        try:
            # 获取当前状态
            cmd = ["kubectl", "get", "nodeguardianrule", rule_name, "-o", "jsonpath={.status.triggeredNodes}"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            current_triggered_nodes = json.loads(result.stdout) if result.stdout else []
            
            # 移除恢复的节点
            updated_nodes = [node for node in current_triggered_nodes if node != node_name]
            
            # 更新状态
            status_patch = {
                "status": {
                    "triggeredNodes": updated_nodes,
                    "lastRecovery": self.get_current_timestamp()
                }
            }
            
            cmd = ["kubectl", "patch", "nodeguardianrule", rule_name, "--type=merge", "--patch", json.dumps(status_patch)]
            subprocess.run(cmd, check=True)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to update rule recovery status for {rule_name}: {e}")
    
    def get_matching_nodes(self, node_selector: Dict[str, Any]) -> List[str]:
        """获取匹配节点选择器的节点"""
        try:
            # 构建kubectl命令
            cmd = ["kubectl", "get", "nodes", "-o", "json"]
            
            # 如果有标签选择器，添加--selector参数
            if node_selector:
                selector_parts = []
                for key, value in node_selector.items():
                    selector_parts.append(f"{key}={value}")
                if selector_parts:
                    cmd.extend(["--selector", ",".join(selector_parts)])
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            nodes_data = json.loads(result.stdout)
            
            return [node['metadata']['name'] for node in nodes_data.get('items', [])]
            
        except Exception as e:
            logger.error(f"Failed to get matching nodes: {e}")
            return []
    
    def get_metric_value(self, metric: str, node_name: str) -> Optional[float]:
        """获取指标值"""
        try:
            if metric == "cpuUtilizationPercent":
                return self.get_node_cpu_utilization(node_name)
            elif metric == "memoryUtilizationPercent":
                return self.get_node_memory_utilization(node_name)
            elif metric == "diskUtilizationPercent":
                return self.get_node_disk_utilization(node_name)
            elif metric == "cpuLoadRatio":
                return self.get_node_cpu_load_ratio(node_name)
            else:
                logger.error(f"Unknown metric type: {metric}")
                return None
        except Exception as e:
            logger.error(f"Failed to get metric {metric} for node {node_name}: {e}")
            return None
    
    def get_node_cpu_utilization(self, node_name: str) -> Optional[float]:
        """获取节点CPU使用率"""
        try:
            # 使用kubectl top命令获取CPU使用率
            cmd = ["kubectl", "top", "node", node_name, "--no-headers"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # 解析输出，格式通常是: "node-name 100m 1Gi"
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                cpu_str = parts[1]
                # 移除'm'后缀并转换为百分比
                if cpu_str.endswith('m'):
                    cpu_millicores = int(cpu_str[:-1])
                    # 假设节点有2个CPU核心，每个1000m
                    cpu_cores = 2
                    return (cpu_millicores / (cpu_cores * 1000)) * 100
            return None
        except Exception as e:
            logger.error(f"Failed to get CPU utilization for node {node_name}: {e}")
            return None
    
    def get_node_memory_utilization(self, node_name: str) -> Optional[float]:
        """获取节点内存使用率"""
        try:
            # 使用kubectl top命令获取内存使用率
            cmd = ["kubectl", "top", "node", node_name, "--no-headers"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # 解析输出，格式通常是: "node-name 100m 1Gi"
            parts = result.stdout.strip().split()
            if len(parts) >= 3:
                memory_str = parts[2]
                # 这里需要获取节点的总内存来计算使用率
                # 简化处理，返回一个模拟值
                return 45.0  # 模拟45%内存使用率（恢复状态）
            return None
        except Exception as e:
            logger.error(f"Failed to get memory utilization for node {node_name}: {e}")
            return None
    
    def get_node_disk_utilization(self, node_name: str) -> Optional[float]:
        """获取节点磁盘使用率"""
        try:
            # 这里需要实现获取节点磁盘使用率的逻辑
            # 简化处理，返回一个模拟值
            return 40.0  # 模拟40%磁盘使用率（恢复状态）
        except Exception as e:
            logger.error(f"Failed to get disk utilization for node {node_name}: {e}")
            return None
    
    def get_node_cpu_load_ratio(self, node_name: str) -> Optional[float]:
        """获取节点CPU负载比"""
        try:
            # 这里需要实现获取节点CPU负载比的逻辑
            # 简化处理，返回一个模拟值
            return 0.8  # 模拟0.8的负载比（恢复状态）
        except Exception as e:
            logger.error(f"Failed to get CPU load ratio for node {node_name}: {e}")
            return None
    
    def evaluate_condition(self, metric_value: float, operator: str, threshold: float) -> bool:
        """评估条件"""
        try:
            if operator == ">":
                return metric_value > threshold
            elif operator == ">=":
                return metric_value >= threshold
            elif operator == "<":
                return metric_value < threshold
            elif operator == "<=":
                return metric_value <= threshold
            elif operator == "==":
                return abs(metric_value - threshold) < 0.001
            elif operator == "!=":
                return abs(metric_value - threshold) >= 0.001
            else:
                logger.error(f"Unknown operator: {operator}")
                return False
        except Exception as e:
            logger.error(f"Error evaluating condition: {e}")
            return False
    
    def check_cooldown(self, rule_name: str, node_name: str, cooldown_period: str) -> bool:
        """检查冷却期"""
        try:
            cooldown_file = f"{self.cooldown_dir}/{rule_name}_{node_name}"
            if not os.path.exists(cooldown_file):
                return False
            
            # 检查文件修改时间
            import time
            file_mtime = os.path.getmtime(cooldown_file)
            current_time = time.time()
            
            # 解析冷却期（简化处理，假设格式为"2m"）
            if cooldown_period.endswith('m'):
                cooldown_seconds = int(cooldown_period[:-1]) * 60
            elif cooldown_period.endswith('s'):
                cooldown_seconds = int(cooldown_period[:-1])
            else:
                cooldown_seconds = 120  # 默认2分钟
            
            return (current_time - file_mtime) < cooldown_seconds
            
        except Exception as e:
            logger.error(f"Error checking cooldown: {e}")
            return False
    
    def set_cooldown(self, rule_name: str, node_name: str) -> None:
        """设置冷却期"""
        try:
            cooldown_file = f"{self.cooldown_dir}/{rule_name}_{node_name}"
            Path(cooldown_file).touch()
        except Exception as e:
            logger.error(f"Error setting cooldown: {e}")
    
    def get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"

def main():
    """主函数"""
    recovery_manager = RecoveryManager()
    recovery_manager.run(sys.argv[1:])

if __name__ == "__main__":
    main()
