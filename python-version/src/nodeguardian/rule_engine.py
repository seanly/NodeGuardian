"""Rule engine for evaluating NodeGuardianRule conditions."""

import json
import time
import os
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from .common import Logger, NodeGuardianConfig, MetricsCollector, KubernetesClient


@dataclass
class Condition:
    """Represents a single condition in a rule."""
    
    metric: str
    operator: str
    value: float
    duration: str = "5m"
    description: str = ""


@dataclass
class Rule:
    """Represents a NodeGuardianRule."""
    
    name: str
    conditions: List[Condition]
    condition_logic: str = "AND"
    node_selector: Dict[str, Any]
    actions: List[Dict[str, Any]]
    recovery_conditions: List[Condition]
    recovery_actions: List[Dict[str, Any]]
    monitoring: Dict[str, Any]
    metadata: Dict[str, Any]
    enabled: bool = True


class RuleEngine:
    """Engine for evaluating rules and executing actions."""
    
    def __init__(self, config: NodeGuardianConfig):
        self.config = config
        self.logger = Logger("rule-engine")
        self.metrics_collector = MetricsCollector(config)
        self.k8s_client = KubernetesClient(config)
        self.rules_dir = "/tmp/nodeguardian/rules"
        self.cooldown_dir = "/tmp/nodeguardian/cooldown"
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        os.makedirs(self.rules_dir, exist_ok=True)
        os.makedirs(self.cooldown_dir, exist_ok=True)
    
    def load_rule(self, rule_data: Dict[str, Any]) -> Rule:
        """Load a rule from dictionary data."""
        conditions = []
        for cond_data in rule_data.get("spec", {}).get("conditions", []):
            conditions.append(Condition(
                metric=cond_data["metric"],
                operator=cond_data["operator"],
                value=float(cond_data["value"]),
                duration=cond_data.get("duration", "5m"),
                description=cond_data.get("description", "")
            ))
        
        recovery_conditions = []
        for cond_data in rule_data.get("spec", {}).get("recoveryConditions", []):
            recovery_conditions.append(Condition(
                metric=cond_data["metric"],
                operator=cond_data["operator"],
                value=float(cond_data["value"]),
                duration=cond_data.get("duration", "5m"),
                description=cond_data.get("description", "")
            ))
        
        return Rule(
            name=rule_data["metadata"]["name"],
            conditions=conditions,
            condition_logic=rule_data.get("spec", {}).get("conditionLogic", "AND"),
            node_selector=rule_data.get("spec", {}).get("nodeSelector", {}),
            actions=rule_data.get("spec", {}).get("actions", []),
            recovery_conditions=recovery_conditions,
            recovery_actions=rule_data.get("spec", {}).get("recoveryActions", []),
            monitoring=rule_data.get("spec", {}).get("monitoring", {}),
            metadata=rule_data.get("spec", {}).get("metadata", {}),
            enabled=rule_data.get("spec", {}).get("metadata", {}).get("enabled", True)
        )
    
    def save_rule(self, rule: Rule) -> None:
        """Save a rule to disk."""
        rule_file = os.path.join(self.rules_dir, f"{rule.name}.json")
        rule_data = {
            "metadata": {"name": rule.name},
            "spec": {
                "conditions": [
                    {
                        "metric": c.metric,
                        "operator": c.operator,
                        "value": c.value,
                        "duration": c.duration,
                        "description": c.description
                    } for c in rule.conditions
                ],
                "conditionLogic": rule.condition_logic,
                "nodeSelector": rule.node_selector,
                "actions": rule.actions,
                "recoveryConditions": [
                    {
                        "metric": c.metric,
                        "operator": c.operator,
                        "value": c.value,
                        "duration": c.duration,
                        "description": c.description
                    } for c in rule.recovery_conditions
                ],
                "recoveryActions": rule.recovery_actions,
                "monitoring": rule.monitoring,
                "metadata": rule.metadata
            }
        }
        
        with open(rule_file, 'w') as f:
            json.dump(rule_data, f, indent=2)
        
        self.logger.info(f"Saved rule: {rule.name}")
    
    def load_rule_from_file(self, rule_name: str) -> Optional[Rule]:
        """Load a rule from file."""
        rule_file = os.path.join(self.rules_dir, f"{rule_name}.json")
        if not os.path.exists(rule_file):
            return None
        
        try:
            with open(rule_file, 'r') as f:
                rule_data = json.load(f)
            return self.load_rule(rule_data)
        except Exception as e:
            self.logger.error(f"Failed to load rule {rule_name}: {e}")
            return None
    
    def delete_rule(self, rule_name: str) -> None:
        """Delete a rule file."""
        rule_file = os.path.join(self.rules_dir, f"{rule_name}.json")
        if os.path.exists(rule_file):
            os.remove(rule_file)
            self.logger.info(f"Deleted rule: {rule_name}")
        
        # Clean up cooldown files
        cooldown_pattern = os.path.join(self.cooldown_dir, f"{rule_name}_*")
        import glob
        for cooldown_file in glob.glob(cooldown_pattern):
            os.remove(cooldown_file)
    
    def get_matching_nodes(self, node_selector: Dict[str, Any]) -> List[str]:
        """Get nodes matching the selector."""
        if "nodeNames" in node_selector:
            return node_selector["nodeNames"]
        
        # Build label selector
        label_selector = ""
        if "matchLabels" in node_selector:
            labels = []
            for key, value in node_selector["matchLabels"].items():
                labels.append(f"{key}={value}")
            label_selector = ",".join(labels)
        
        nodes = self.k8s_client.get_nodes(label_selector=label_selector if label_selector else None)
        return [node["name"] for node in nodes]
    
    def evaluate_condition(self, condition: Condition, node_name: str) -> bool:
        """Evaluate a single condition for a node."""
        try:
            metric_value = self.metrics_collector.get_node_metrics(node_name, condition.metric)
            
            if condition.operator == "GreaterThan":
                return metric_value > condition.value
            elif condition.operator == "LessThan":
                return metric_value < condition.value
            elif condition.operator == "EqualTo":
                return abs(metric_value - condition.value) < 0.001
            elif condition.operator == "NotEqualTo":
                return abs(metric_value - condition.value) >= 0.001
            elif condition.operator == "GreaterThanOrEqual":
                return metric_value >= condition.value
            elif condition.operator == "LessThanOrEqual":
                return metric_value <= condition.value
            else:
                self.logger.error(f"Unknown operator: {condition.operator}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to evaluate condition for node {node_name}: {e}")
            return False
    
    def evaluate_rule_conditions(self, rule: Rule, node_name: str) -> bool:
        """Evaluate all conditions for a rule on a specific node."""
        if not rule.conditions:
            return False
        
        satisfied_conditions = 0
        total_conditions = len(rule.conditions)
        
        for condition in rule.conditions:
            if self.evaluate_condition(condition, node_name):
                satisfied_conditions += 1
                self.logger.debug(
                    f"Condition satisfied for node {node_name}",
                    condition=condition.description,
                    metric=condition.metric,
                    operator=condition.operator,
                    threshold=condition.value
                )
            else:
                self.logger.debug(
                    f"Condition not satisfied for node {node_name}",
                    condition=condition.description,
                    metric=condition.metric,
                    operator=condition.operator,
                    threshold=condition.value
                )
        
        if rule.condition_logic == "AND":
            return satisfied_conditions == total_conditions
        else:  # OR
            return satisfied_conditions > 0
    
    def is_in_cooldown(self, rule_name: str, node_name: str) -> bool:
        """Check if a rule is in cooldown period for a specific node."""
        cooldown_file = os.path.join(self.cooldown_dir, f"{rule_name}_{node_name}")
        if not os.path.exists(cooldown_file):
            return False
        
        try:
            with open(cooldown_file, 'r') as f:
                last_triggered = float(f.read().strip())
            
            cooldown_period = self._parse_duration(rule.monitoring.get("cooldownPeriod", "5m"))
            current_time = time.time()
            
            return (current_time - last_triggered) < cooldown_period
        except Exception as e:
            self.logger.error(f"Failed to check cooldown for {rule_name}/{node_name}: {e}")
            return False
    
    def set_cooldown(self, rule_name: str, node_name: str) -> None:
        """Set cooldown period for a rule and node."""
        cooldown_file = os.path.join(self.cooldown_dir, f"{rule_name}_{node_name}")
        with open(cooldown_file, 'w') as f:
            f.write(str(time.time()))
    
    def _parse_duration(self, duration: str) -> int:
        """Parse duration string to seconds."""
        if duration.endswith('s'):
            return int(duration[:-1])
        elif duration.endswith('m'):
            return int(duration[:-1]) * 60
        elif duration.endswith('h'):
            return int(duration[:-1]) * 3600
        elif duration.endswith('d'):
            return int(duration[:-1]) * 86400
        else:
            return int(duration)
    
    def evaluate_rule(self, rule: Rule) -> List[str]:
        """Evaluate a rule and return list of triggered nodes."""
        if not rule.enabled:
            return []
        
        self.logger.debug(f"Evaluating rule: {rule.name}")
        
        # Get matching nodes
        matching_nodes = self.get_matching_nodes(rule.node_selector)
        if not matching_nodes:
            self.logger.warning(f"No matching nodes found for rule: {rule.name}")
            return []
        
        triggered_nodes = []
        
        for node_name in matching_nodes:
            # Check cooldown
            if self.is_in_cooldown(rule.name, node_name):
                self.logger.debug(f"Rule {rule.name} for node {node_name} is in cooldown")
                continue
            
            # Evaluate conditions
            if self.evaluate_rule_conditions(rule, node_name):
                triggered_nodes.append(node_name)
        
        return triggered_nodes
    
    def execute_actions(self, rule: Rule, triggered_nodes: List[str]) -> None:
        """Execute actions for triggered nodes."""
        if not triggered_nodes:
            return
        
        self.logger.info(f"Executing actions for rule {rule.name} on nodes: {triggered_nodes}")
        
        for action in rule.actions:
            try:
                self._execute_action(action, rule, triggered_nodes)
            except Exception as e:
                self.logger.error(f"Failed to execute action {action.get('type', 'unknown')}: {e}")
        
        # Set cooldown for all triggered nodes
        for node_name in triggered_nodes:
            self.set_cooldown(rule.name, node_name)
        
        # Update rule status
        self.k8s_client.update_rule_status(
            rule.name,
            "Active",
            "Rule triggered",
            triggered_nodes
        )
    
    def _execute_action(self, action: Dict[str, Any], rule: Rule, triggered_nodes: List[str]) -> None:
        """Execute a single action."""
        action_type = action.get("type")
        
        if action_type == "taint":
            self._execute_taint_action(action, triggered_nodes)
        elif action_type == "alert":
            self._execute_alert_action(action, rule, triggered_nodes)
        elif action_type == "evict":
            self._execute_evict_action(action, triggered_nodes)
        elif action_type == "label":
            self._execute_label_action(action, triggered_nodes)
        elif action_type == "annotation":
            self._execute_annotation_action(action, triggered_nodes)
        else:
            self.logger.warning(f"Unknown action type: {action_type}")
    
    def _execute_taint_action(self, action: Dict[str, Any], triggered_nodes: List[str]) -> None:
        """Execute taint action."""
        taint_config = action.get("taint", {})
        key = taint_config.get("key", "nodeguardian/rule-triggered")
        value = taint_config.get("value", "true")
        effect = taint_config.get("effect", "NoSchedule")
        
        for node_name in triggered_nodes:
            self.k8s_client.taint_node(node_name, key, value, effect)
    
    def _execute_alert_action(self, action: Dict[str, Any], rule: Rule, triggered_nodes: List[str]) -> None:
        """Execute alert action."""
        alert_config = action.get("alert", {})
        if not alert_config.get("enabled", True):
            return
        
        template_name = alert_config.get("template", "default")
        channels = alert_config.get("channels", [])
        
        # Import here to avoid circular imports
        from .alert_manager import AlertManager
        
        alert_manager = AlertManager(self.config)
        alert_manager.send_alert(template_name, rule, triggered_nodes, channels)
    
    def _execute_evict_action(self, action: Dict[str, Any], triggered_nodes: List[str]) -> None:
        """Execute evict action."""
        evict_config = action.get("evict", {})
        max_pods = evict_config.get("maxPods", 10)
        exclude_namespaces = evict_config.get("excludeNamespaces", ["kube-system", "kube-public"])
        
        for node_name in triggered_nodes:
            pods = self.k8s_client.get_pods_on_node(node_name, exclude_namespaces)
            
            evicted_count = 0
            for pod in pods[:max_pods]:
                if self.k8s_client.delete_pod(pod["namespace"], pod["name"]):
                    evicted_count += 1
            
            self.logger.info(f"Evicted {evicted_count} pods from node {node_name}")
    
    def _execute_label_action(self, action: Dict[str, Any], triggered_nodes: List[str]) -> None:
        """Execute label action."""
        label_config = action.get("label", {})
        labels = label_config.get("labels", {})
        
        for node_name in triggered_nodes:
            self.k8s_client.label_node(node_name, labels)
    
    def _execute_annotation_action(self, action: Dict[str, Any], triggered_nodes: List[str]) -> None:
        """Execute annotation action."""
        annotation_config = action.get("annotation", {})
        annotations = annotation_config.get("annotations", {})
        
        for node_name in triggered_nodes:
            self.k8s_client.annotate_node(node_name, annotations)
    
    def evaluate_all_rules(self) -> None:
        """Evaluate all active rules."""
        if not os.path.exists(self.rules_dir):
            return
        
        rule_files = [f for f in os.listdir(self.rules_dir) if f.endswith('.json')]
        
        for rule_file in rule_files:
            rule_name = rule_file[:-5]  # Remove .json extension
            rule = self.load_rule_from_file(rule_name)
            
            if rule:
                triggered_nodes = self.evaluate_rule(rule)
                if triggered_nodes:
                    self.execute_actions(rule, triggered_nodes)
