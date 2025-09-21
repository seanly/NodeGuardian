#!/usr/bin/env python3
"""
NodeGuardian Main Controller Python Script
处理NodeGuardianRule CRD变化并管理规则生命周期
"""

import json
import os
import sys
import logging
import subprocess
from typing import Dict, List, Any, Optional
from pathlib import Path

# 导入配置加载器
from config_loader import get_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NodeGuardianController:
    """NodeGuardian主控制器"""
    
    def __init__(self):
        self.config_dir = "/etc/nodeguardian/config"
        self.secrets_dir = "/etc/nodeguardian/secrets"
        self.config_file = f"{self.config_dir}/config.json"
        self.rules_dir = "/tmp/nodeguardian/rules"
        self.templates_dir = "/tmp/nodeguardian/templates"
        self.cooldown_dir = "/tmp/nodeguardian/cooldown"
        
        # 确保目录存在
        Path(self.rules_dir).mkdir(parents=True, exist_ok=True)
        Path(self.templates_dir).mkdir(parents=True, exist_ok=True)
        Path(self.cooldown_dir).mkdir(parents=True, exist_ok=True)
        
        # 加载配置
        self.config = get_config()
    
    def run(self, args: List[str]) -> None:  # pylint: disable=unused-argument
        """主运行函数"""
        try:
            # 读取绑定上下文
            binding_context_path = os.environ.get('BINDING_CONTEXT_PATH', '/tmp/binding_context.json')
            
            if not os.path.exists(binding_context_path):
                logger.error(f"Binding context file not found: {binding_context_path}")
                sys.exit(1)
            
            with open(binding_context_path, 'r', encoding='utf-8') as f:
                binding_context = json.load(f)
            
            if not binding_context:
                logger.error("Empty binding context")
                sys.exit(1)
            
            # 处理绑定上下文
            context_type = binding_context[0].get('type')
            binding = binding_context[0].get('binding')
            
            logger.info(f"Processing binding context: type={context_type}, binding={binding}")
            
            if context_type == "onStartup":
                self.handle_startup()
            elif context_type == "Synchronization":
                self.handle_synchronization(binding, binding_context[0])
            elif context_type == "Event":
                self.handle_event(binding, binding_context[0])
            elif context_type == "Schedule":
                self.handle_schedule(binding)
            else:
                logger.warning(f"Unknown binding context type: {context_type}")
                
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error in main run: {e}")
            sys.exit(1)
    
    def handle_startup(self) -> None:
        """处理启动事件"""
        logger.info("NodeGuardian controller starting up...")
        
        # 创建必要的资源
        self.create_namespace_if_not_exists()
        self.create_configmap_if_not_exists()
        
        # 初始化所有现有规则
        self.initialize_existing_rules()
        
        logger.info("NodeGuardian controller startup completed")
    
    def handle_synchronization(self, binding: str, context: Dict[str, Any]) -> None:
        """处理同步事件"""
        if binding == "monitor-nodeguardian-rules":
            self.handle_rules_synchronization(context)
        elif binding == "monitor-alert-templates":
            self.handle_templates_synchronization(context)
    
    def handle_rules_synchronization(self, context: Dict[str, Any]) -> None:
        """处理规则同步"""
        objects = context.get('objects', [])
        logger.info(f"Synchronizing {len(objects)} NodeGuardianRule objects")
        
        for obj in objects:
            rule_object = obj.get('object', {})
            rule_name = rule_object.get('metadata', {}).get('name')
            rule_enabled = rule_object.get('spec', {}).get('metadata', {}).get('enabled', True)
            
            if rule_enabled:
                self.register_rule(rule_object)
            else:
                self.unregister_rule(rule_name)
    
    def handle_templates_synchronization(self, context: Dict[str, Any]) -> None:
        """处理模板同步"""
        objects = context.get('objects', [])
        logger.info(f"Synchronizing {len(objects)} AlertTemplate objects")
        
        for obj in objects:
            template_object = obj.get('object', {})
            self.register_alert_template(template_object)
    
    def handle_event(self, binding: str, context: Dict[str, Any]) -> None:
        """处理事件"""
        watch_event = context.get('watchEvent')
        object_data = context.get('object', {})
        
        if binding == "monitor-nodeguardian-rules":
            self.handle_rule_event(watch_event, object_data)
        elif binding == "monitor-alert-templates":
            self.handle_template_event(watch_event, object_data)
    
    def handle_rule_event(self, watch_event: str, rule_object: Dict[str, Any]) -> None:
        """处理规则事件"""
        rule_name = rule_object.get('metadata', {}).get('name')
        logger.info(f"Processing rule event: {watch_event} for rule: {rule_name}")
        
        if watch_event in ["Added", "Modified"]:
            rule_enabled = rule_object.get('spec', {}).get('metadata', {}).get('enabled', True)
            if rule_enabled:
                self.register_rule(rule_object)
            else:
                self.unregister_rule(rule_name)
        elif watch_event == "Deleted":
            self.unregister_rule(rule_name)
    
    def handle_template_event(self, watch_event: str, template_object: Dict[str, Any]) -> None:
        """处理模板事件"""
        template_name = template_object.get('metadata', {}).get('name')
        logger.info(f"Processing template event: {watch_event} for template: {template_name}")
        
        if watch_event in ["Added", "Modified"]:
            self.register_alert_template(template_object)
        elif watch_event == "Deleted":
            self.unregister_alert_template(template_name)
    
    def handle_schedule(self, binding: str) -> None:
        """处理定时任务"""
        if binding == "rule-evaluation":
            self.evaluate_all_rules()
    
    def register_rule(self, rule_object: Dict[str, Any]) -> None:
        """注册规则"""
        rule_name = rule_object.get('metadata', {}).get('name')
        check_interval = rule_object.get('spec', {}).get('monitoring', {}).get('checkInterval', '60s')
        
        logger.info(f"Registering rule: {rule_name} with check interval: {check_interval}")
        
        # 保存规则到文件
        rule_file = f"{self.rules_dir}/{rule_name}.json"
        with open(rule_file, 'w') as f:
            json.dump(rule_object, f, indent=2)
        
        # 更新状态
        self.update_rule_status(rule_name, "Active", "", [])
        
        logger.info(f"Rule registered: {rule_name}")
    
    def unregister_rule(self, rule_name: str) -> None:
        """注销规则"""
        logger.info(f"Unregistering rule: {rule_name}")
        
        # 删除规则文件
        rule_file = f"{self.rules_dir}/{rule_name}.json"
        if os.path.exists(rule_file):
            os.remove(rule_file)
        
        # 清理冷却期文件
        for cooldown_file in Path(self.cooldown_dir).glob(f"{rule_name}_*"):
            cooldown_file.unlink()
        
        # 更新状态
        self.update_rule_status(rule_name, "Inactive", "Rule deleted", [])
        
        logger.info(f"Rule unregistered: {rule_name}")
    
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
    
    def evaluate_all_rules(self) -> None:
        """评估所有规则"""
        if not os.path.exists(self.rules_dir):
            return
        
        logger.debug("Evaluating all active rules...")
        
        for rule_file in Path(self.rules_dir).glob("*.json"):
            if rule_file.is_file():
                rule_name = rule_file.stem
                self.evaluate_rule(str(rule_file))
    
    def evaluate_rule(self, rule_file: str) -> None:
        """评估单个规则"""
        try:
            with open(rule_file, 'r') as f:
                rule_object = json.load(f)
            
            rule_name = rule_object.get('metadata', {}).get('name')
            rule_enabled = rule_object.get('spec', {}).get('metadata', {}).get('enabled', True)
            
            if not rule_enabled:
                return
            
            logger.debug(f"Evaluating rule: {rule_name}")
            
            # 获取节点选择器
            node_selector = rule_object.get('spec', {}).get('nodeSelector', {})
            matching_nodes = self.get_matching_nodes(node_selector)
            
            if not matching_nodes:
                logger.warning(f"No matching nodes found for rule: {rule_name}")
                return
            
            # 评估每个节点
            triggered_nodes = []
            for node_name in matching_nodes:
                if self.evaluate_node_for_rule(rule_object, node_name):
                    triggered_nodes.append(node_name)
            
            # 如果有节点触发，执行动作
            if triggered_nodes:
                self.execute_rule_actions(rule_object, triggered_nodes)
                self.update_rule_status(rule_name, "Active", "Rule triggered", triggered_nodes)
                
        except Exception as e:
            logger.error(f"Error evaluating rule {rule_file}: {e}")
    
    def evaluate_node_for_rule(self, rule_object: Dict[str, Any], node_name: str) -> bool:
        """评估节点是否满足规则条件"""
        rule_name = rule_object.get('metadata', {}).get('name')
        
        # 检查冷却期
        cooldown_period = rule_object.get('spec', {}).get('monitoring', {}).get('cooldownPeriod', '5m')
        if self.check_cooldown(rule_name, node_name, cooldown_period):
            logger.debug(f"Rule {rule_name} for node {node_name} is in cooldown period")
            return False
        
        # 获取条件
        conditions = rule_object.get('spec', {}).get('conditions', [])
        condition_logic = rule_object.get('spec', {}).get('conditionLogic', 'AND')
        
        satisfied_conditions = 0
        
        # 评估每个条件
        for condition in conditions:
            metric = condition.get('metric')
            operator = condition.get('operator')
            threshold = condition.get('value')
            duration = condition.get('duration', '5m')
            
            # 获取指标值
            metric_value = self.get_metric_value(metric, node_name)
            if metric_value is None:
                logger.error(f"Failed to get metric value for {metric} on node {node_name}")
                continue
            
            # 评估条件
            if self.evaluate_condition(metric_value, operator, threshold):
                satisfied_conditions += 1
                logger.debug(f"Condition satisfied for node {node_name}: {metric} {operator} {threshold} (value: {metric_value})")
            else:
                logger.debug(f"Condition not satisfied for node {node_name}: {metric} {operator} {threshold} (value: {metric_value})")
        
        # 根据逻辑判断是否触发
        if condition_logic == "AND":
            return satisfied_conditions == len(conditions)
        else:  # OR
            return satisfied_conditions > 0
    
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
                return 75.0  # 模拟75%内存使用率
            return None
        except Exception as e:
            logger.error(f"Failed to get memory utilization for node {node_name}: {e}")
            return None
    
    def get_node_disk_utilization(self, node_name: str) -> Optional[float]:
        """获取节点磁盘使用率"""
        try:
            # 这里需要实现获取节点磁盘使用率的逻辑
            # 简化处理，返回一个模拟值
            return 60.0  # 模拟60%磁盘使用率
        except Exception as e:
            logger.error(f"Failed to get disk utilization for node {node_name}: {e}")
            return None
    
    def get_node_cpu_load_ratio(self, node_name: str) -> Optional[float]:
        """获取节点CPU负载比"""
        try:
            # 这里需要实现获取节点CPU负载比的逻辑
            # 简化处理，返回一个模拟值
            return 1.5  # 模拟1.5的负载比
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
            
            # 解析冷却期（简化处理，假设格式为"5m"）
            if cooldown_period.endswith('m'):
                cooldown_seconds = int(cooldown_period[:-1]) * 60
            elif cooldown_period.endswith('s'):
                cooldown_seconds = int(cooldown_period[:-1])
            else:
                cooldown_seconds = 300  # 默认5分钟
            
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
    
    def execute_rule_actions(self, rule_object: Dict[str, Any], triggered_nodes: List[str]) -> None:
        """执行规则动作"""
        rule_name = rule_object.get('metadata', {}).get('name')
        actions = rule_object.get('spec', {}).get('actions', [])
        
        logger.info(f"Executing actions for rule: {rule_name} on nodes: {triggered_nodes}")
        
        for action in actions:
            action_type = action.get('type')
            
            if action_type == "taint":
                self.execute_taint_action(action, triggered_nodes)
            elif action_type == "alert":
                self.execute_alert_action(action, rule_object, triggered_nodes)
            elif action_type == "evict":
                self.execute_evict_action(action, triggered_nodes)
            elif action_type == "label":
                self.execute_label_action(action, triggered_nodes)
            elif action_type == "annotation":
                self.execute_annotation_action(action, triggered_nodes)
            else:
                logger.warning(f"Unknown action type: {action_type}")
        
        # 设置冷却期
        cooldown_period = rule_object.get('spec', {}).get('monitoring', {}).get('cooldownPeriod', '5m')
        for node_name in triggered_nodes:
            self.set_cooldown(rule_name, node_name)
    
    def execute_taint_action(self, action: Dict[str, Any], triggered_nodes: List[str]) -> None:
        """执行污点动作"""
        taint_key = action.get('taint', {}).get('key', 'nodeguardian/rule-triggered')
        taint_value = action.get('taint', {}).get('value', 'true')
        taint_effect = action.get('taint', {}).get('effect', 'NoSchedule')
        
        for node_name in triggered_nodes:
            logger.info(f"Adding taint to node {node_name}: {taint_key}={taint_value}:{taint_effect}")
            try:
                cmd = ["kubectl", "taint", "nodes", node_name, f"{taint_key}={taint_value}:{taint_effect}", "--overwrite"]
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to add taint to node {node_name}: {e}")
    
    def execute_alert_action(self, action: Dict[str, Any], rule_object: Dict[str, Any], triggered_nodes: List[str]) -> None:
        """执行告警动作"""
        alert_enabled = action.get('alert', {}).get('enabled', True)
        if not alert_enabled:
            return
        
        template_name = action.get('alert', {}).get('template', 'default')
        channels = action.get('alert', {}).get('channels', [])
        
        # 调用告警管理器
        try:
            cmd = ["python3", "/scripts/alert_manager.py", template_name, json.dumps(rule_object), json.dumps(triggered_nodes), json.dumps(channels)]
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to send alert: {e}")
    
    def execute_evict_action(self, action: Dict[str, Any], triggered_nodes: List[str]) -> None:
        """执行驱逐动作"""
        max_pods = action.get('evict', {}).get('maxPods', 10)
        exclude_namespaces = action.get('evict', {}).get('excludeNamespaces', ["kube-system", "kube-public"])
        
        for node_name in triggered_nodes:
            logger.info(f"Evicting pods from node {node_name} (max: {max_pods})")
            
            try:
                # 获取节点上的Pod
                cmd = ["kubectl", "get", "pods", "--all-namespaces", "-o", "json", "--field-selector", f"spec.nodeName={node_name}"]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                pods_data = json.loads(result.stdout)
                
                evicted_count = 0
                for pod in pods_data.get('items', []):
                    if evicted_count >= max_pods:
                        break
                    
                    namespace = pod['metadata']['namespace']
                    pod_name = pod['metadata']['name']
                    
                    if namespace not in exclude_namespaces:
                        logger.info(f"Evicting pod: {namespace}/{pod_name}")
                        cmd = ["kubectl", "delete", "pod", f"{namespace}/{pod_name}", "--grace-period=30"]
                        subprocess.run(cmd, check=True)
                        evicted_count += 1
                        
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to evict pods from node {node_name}: {e}")
    
    def execute_label_action(self, action: Dict[str, Any], triggered_nodes: List[str]) -> None:
        """执行标签动作"""
        labels = action.get('label', {}).get('labels', {})
        
        for node_name in triggered_nodes:
            logger.info(f"Adding labels to node {node_name}: {labels}")
            
            try:
                label_args = []
                for key, value in labels.items():
                    label_args.extend([f"{key}={value}"])
                
                if label_args:
                    cmd = ["kubectl", "label", "nodes", node_name] + label_args + ["--overwrite"]
                    subprocess.run(cmd, check=True)
                    
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to add labels to node {node_name}: {e}")
    
    def execute_annotation_action(self, action: Dict[str, Any], triggered_nodes: List[str]) -> None:
        """执行注解动作"""
        annotations = action.get('annotation', {}).get('annotations', {})
        
        for node_name in triggered_nodes:
            logger.info(f"Adding annotations to node {node_name}: {annotations}")
            
            try:
                annotation_args = []
                for key, value in annotations.items():
                    annotation_args.extend([f"{key}={value}"])
                
                if annotation_args:
                    cmd = ["kubectl", "annotate", "nodes", node_name] + annotation_args + ["--overwrite"]
                    subprocess.run(cmd, check=True)
                    
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to add annotations to node {node_name}: {e}")
    
    def update_rule_status(self, rule_name: str, status: str, message: str, triggered_nodes: List[str]) -> None:
        """更新规则状态"""
        try:
            status_patch = {
                "status": {
                    "status": status,
                    "message": message,
                    "triggeredNodes": triggered_nodes,
                    "lastUpdate": self.get_current_timestamp()
                }
            }
            
            cmd = ["kubectl", "patch", "nodeguardianrule", rule_name, "--type=merge", "--patch", json.dumps(status_patch)]
            subprocess.run(cmd, check=True)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to update rule status for {rule_name}: {e}")
    
    def create_namespace_if_not_exists(self) -> None:
        """创建命名空间"""
        namespace = "nodeguardian-system"
        try:
            cmd = ["kubectl", "get", "namespace", namespace]
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.info(f"Creating namespace: {namespace}")
            cmd = ["kubectl", "create", "namespace", namespace]
            subprocess.run(cmd, check=True)
    
    def create_configmap_if_not_exists(self) -> None:
        """创建配置映射"""
        namespace = "nodeguardian-system"
        try:
            cmd = ["kubectl", "get", "configmap", "nodeguardian-config", "-n", namespace]
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.info("Creating configmap: nodeguardian-config")
            # 这里可以创建默认的configmap
            pass
    
    def initialize_existing_rules(self) -> None:
        """初始化现有规则"""
        logger.info("Initializing existing NodeGuardianRule objects...")
        # 这里会在同步阶段处理
        pass
    
    def get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"

def main():
    """主函数"""
    controller = NodeGuardianController()
    controller.run(sys.argv[1:])

if __name__ == "__main__":
    main()
