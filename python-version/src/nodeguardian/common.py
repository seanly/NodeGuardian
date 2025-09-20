"""Common utilities and configuration for NodeGuardian."""

import os
import logging
import structlog
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import requests
import json
import time
from datetime import datetime, timedelta


@dataclass
class NodeGuardianConfig:
    """NodeGuardian configuration."""
    
    namespace: str = "nodeguardian-system"
    metrics_cache_dir: str = "/tmp/nodeguardian/metrics"
    log_level: str = "INFO"
    prometheus_url: str = "http://prometheus-k8s.monitoring.svc:9090"
    metrics_server_url: str = "https://kubernetes.default.svc:443/apis/metrics.k8s.io/v1beta1"
    
    # Alert configuration
    alert_email_smtp: str = "smtp.gmail.com:587"
    alert_email_from: str = "nodeguardian@example.com"
    alert_email_to: str = "admin@example.com"
    alert_slack_webhook: str = ""
    alert_webhook_url: str = ""


class Logger:
    """Structured logger for NodeGuardian."""
    
    def __init__(self, name: str = "nodeguardian", level: str = "INFO"):
        self.logger = structlog.get_logger(name)
        self._setup_logging(level)
    
    def _setup_logging(self, level: str) -> None:
        """Setup structured logging."""
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=getattr(logging, level.upper()),
        )
        
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message."""
        self.logger.error(message, **kwargs)


class KubernetesClient:
    """Kubernetes client wrapper."""
    
    def __init__(self, config_obj: NodeGuardianConfig):
        self.config = config_obj
        self.logger = Logger("kubernetes-client")
        self._setup_client()
    
    def _setup_client(self) -> None:
        """Setup Kubernetes client."""
        try:
            # Try to load in-cluster config first
            config.load_incluster_config()
            self.logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            try:
                # Fall back to kubeconfig
                config.load_kube_config()
                self.logger.info("Loaded kubeconfig")
            except config.ConfigException as e:
                self.logger.error(f"Failed to load Kubernetes config: {e}")
                raise
        
        self.v1 = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()
    
    def get_nodes(self, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get nodes matching the label selector."""
        try:
            nodes = self.v1.list_node(label_selector=label_selector)
            return [self._node_to_dict(node) for node in nodes.items]
        except ApiException as e:
            self.logger.error(f"Failed to get nodes: {e}")
            return []
    
    def get_node_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific node by name."""
        try:
            node = self.v1.read_node(name=name)
            return self._node_to_dict(node)
        except ApiException as e:
            self.logger.error(f"Failed to get node {name}: {e}")
            return None
    
    def taint_node(self, node_name: str, key: str, value: str, effect: str) -> bool:
        """Add taint to a node."""
        try:
            taint = client.V1Taint(
                key=key,
                value=value,
                effect=effect
            )
            
            # Get current node
            node = self.v1.read_node(name=node_name)
            
            # Add taint
            if not node.spec.taints:
                node.spec.taints = []
            node.spec.taints.append(taint)
            
            # Update node
            self.v1.patch_node(name=node_name, body=node)
            self.logger.info(f"Added taint to node {node_name}: {key}={value}:{effect}")
            return True
        except ApiException as e:
            self.logger.error(f"Failed to taint node {node_name}: {e}")
            return False
    
    def remove_taint(self, node_name: str, key: str) -> bool:
        """Remove taint from a node."""
        try:
            # Get current node
            node = self.v1.read_node(name=node_name)
            
            if node.spec.taints:
                # Remove taint with matching key
                node.spec.taints = [t for t in node.spec.taints if t.key != key]
                
                # Update node
                self.v1.patch_node(name=node_name, body=node)
                self.logger.info(f"Removed taint from node {node_name}: {key}")
                return True
            return True
        except ApiException as e:
            self.logger.error(f"Failed to remove taint from node {node_name}: {e}")
            return False
    
    def label_node(self, node_name: str, labels: Dict[str, str]) -> bool:
        """Add labels to a node."""
        try:
            # Get current node
            node = self.v1.read_node(name=node_name)
            
            if not node.metadata.labels:
                node.metadata.labels = {}
            
            # Add labels
            node.metadata.labels.update(labels)
            
            # Update node
            self.v1.patch_node(name=node_name, body=node)
            self.logger.info(f"Added labels to node {node_name}: {labels}")
            return True
        except ApiException as e:
            self.logger.error(f"Failed to label node {node_name}: {e}")
            return False
    
    def remove_labels(self, node_name: str, keys: List[str]) -> bool:
        """Remove labels from a node."""
        try:
            # Get current node
            node = self.v1.read_node(name=node_name)
            
            if node.metadata.labels:
                # Remove specified labels
                for key in keys:
                    node.metadata.labels.pop(key, None)
                
                # Update node
                self.v1.patch_node(name=node_name, body=node)
                self.logger.info(f"Removed labels from node {node_name}: {keys}")
                return True
            return True
        except ApiException as e:
            self.logger.error(f"Failed to remove labels from node {node_name}: {e}")
            return False
    
    def annotate_node(self, node_name: str, annotations: Dict[str, str]) -> bool:
        """Add annotations to a node."""
        try:
            # Get current node
            node = self.v1.read_node(name=node_name)
            
            if not node.metadata.annotations:
                node.metadata.annotations = {}
            
            # Add annotations
            node.metadata.annotations.update(annotations)
            
            # Update node
            self.v1.patch_node(name=node_name, body=node)
            self.logger.info(f"Added annotations to node {node_name}: {annotations}")
            return True
        except ApiException as e:
            self.logger.error(f"Failed to annotate node {node_name}: {e}")
            return False
    
    def remove_annotations(self, node_name: str, keys: List[str]) -> bool:
        """Remove annotations from a node."""
        try:
            # Get current node
            node = self.v1.read_node(name=node_name)
            
            if node.metadata.annotations:
                # Remove specified annotations
                for key in keys:
                    node.metadata.annotations.pop(key, None)
                
                # Update node
                self.v1.patch_node(name=node_name, body=node)
                self.logger.info(f"Removed annotations from node {node_name}: {keys}")
                return True
            return True
        except ApiException as e:
            self.logger.error(f"Failed to remove annotations from node {node_name}: {e}")
            return False
    
    def get_pods_on_node(self, node_name: str, exclude_namespaces: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get pods running on a specific node."""
        try:
            pods = self.v1.list_pod_for_all_namespaces(
                field_selector=f"spec.nodeName={node_name}"
            )
            
            result = []
            exclude_ns = exclude_namespaces or ["kube-system", "kube-public"]
            
            for pod in pods.items:
                if pod.metadata.namespace not in exclude_ns:
                    result.append(self._pod_to_dict(pod))
            
            return result
        except ApiException as e:
            self.logger.error(f"Failed to get pods on node {node_name}: {e}")
            return []
    
    def delete_pod(self, namespace: str, name: str, grace_period: int = 30) -> bool:
        """Delete a pod."""
        try:
            self.v1.delete_namespaced_pod(
                name=name,
                namespace=namespace,
                grace_period_seconds=grace_period
            )
            self.logger.info(f"Deleted pod {namespace}/{name}")
            return True
        except ApiException as e:
            self.logger.error(f"Failed to delete pod {namespace}/{name}: {e}")
            return False
    
    def get_nodeguardian_rules(self) -> List[Dict[str, Any]]:
        """Get all NodeGuardianRule objects."""
        try:
            rules = self.custom_api.list_cluster_custom_object(
                group="nodeguardian.k8s.io",
                version="v1",
                plural="nodeguardianrules"
            )
            return rules.get("items", [])
        except ApiException as e:
            self.logger.error(f"Failed to get NodeGuardianRule objects: {e}")
            return []
    
    def update_rule_status(self, rule_name: str, phase: str, message: str, triggered_nodes: List[str]) -> bool:
        """Update NodeGuardianRule status."""
        try:
            status = {
                "status": {
                    "phase": phase,
                    "lastTriggered": datetime.utcnow().isoformat() + "Z",
                    "triggeredNodes": triggered_nodes,
                    "lastError": message
                }
            }
            
            self.custom_api.patch_cluster_custom_object_status(
                group="nodeguardian.k8s.io",
                version="v1",
                plural="nodeguardianrules",
                name=rule_name,
                body=status
            )
            return True
        except ApiException as e:
            self.logger.error(f"Failed to update rule status for {rule_name}: {e}")
            return False
    
    def _node_to_dict(self, node) -> Dict[str, Any]:
        """Convert Kubernetes node object to dictionary."""
        return {
            "name": node.metadata.name,
            "labels": node.metadata.labels or {},
            "annotations": node.metadata.annotations or {},
            "taints": [{"key": t.key, "value": t.value, "effect": t.effect} for t in (node.spec.taints or [])],
            "capacity": node.status.capacity or {},
            "allocatable": node.status.allocatable or {},
            "conditions": [{"type": c.type, "status": c.status, "reason": c.reason} for c in (node.status.conditions or [])]
        }
    
    def _pod_to_dict(self, pod) -> Dict[str, Any]:
        """Convert Kubernetes pod object to dictionary."""
        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "node_name": pod.spec.node_name,
            "phase": pod.status.phase,
            "labels": pod.metadata.labels or {},
            "annotations": pod.metadata.annotations or {}
        }


class MetricsCollector:
    """Collects node metrics from various sources."""
    
    def __init__(self, config_obj: NodeGuardianConfig):
        self.config = config_obj
        self.logger = Logger("metrics-collector")
        self.k8s_client = KubernetesClient(config_obj)
    
    def get_node_metrics(self, node_name: str, metric_type: str) -> float:
        """Get specific metric for a node."""
        try:
            if metric_type == "cpuUtilizationPercent":
                return self._get_cpu_utilization(node_name)
            elif metric_type == "memoryUtilizationPercent":
                return self._get_memory_utilization(node_name)
            elif metric_type == "diskUtilizationPercent":
                return self._get_disk_utilization(node_name)
            elif metric_type == "cpuLoadRatio":
                return self._get_cpu_load_ratio(node_name)
            else:
                self.logger.error(f"Unknown metric type: {metric_type}")
                return 0.0
        except Exception as e:
            self.logger.error(f"Failed to get metric {metric_type} for node {node_name}: {e}")
            return 0.0
    
    def _get_cpu_utilization(self, node_name: str) -> float:
        """Get CPU utilization percentage."""
        # Try Prometheus first
        if self.config.prometheus_url:
            try:
                query = f'100 - (avg by (instance) (irate(node_cpu_seconds_total{{mode="idle",instance=~".*{node_name}.*"}}[5m])) * 100)'
                result = self._query_prometheus(query)
                if result is not None:
                    return float(result)
            except Exception as e:
                self.logger.debug(f"Prometheus query failed: {e}")
        
        # Fall back to Metrics Server
        try:
            return self._get_cpu_utilization_from_metrics_server(node_name)
        except Exception as e:
            self.logger.debug(f"Metrics Server query failed: {e}")
            return 0.0
    
    def _get_memory_utilization(self, node_name: str) -> float:
        """Get memory utilization percentage."""
        # Try Prometheus first
        if self.config.prometheus_url:
            try:
                query = f'(1 - (node_memory_MemAvailable_bytes{{instance=~".*{node_name}.*"}} / node_memory_MemTotal_bytes{{instance=~".*{node_name}.*"}})) * 100'
                result = self._query_prometheus(query)
                if result is not None:
                    return float(result)
            except Exception as e:
                self.logger.debug(f"Prometheus query failed: {e}")
        
        # Fall back to Metrics Server
        try:
            return self._get_memory_utilization_from_metrics_server(node_name)
        except Exception as e:
            self.logger.debug(f"Metrics Server query failed: {e}")
            return 0.0
    
    def _get_disk_utilization(self, node_name: str) -> float:
        """Get disk utilization percentage."""
        if self.config.prometheus_url:
            try:
                query = f'(1 - (node_filesystem_avail_bytes{{instance=~".*{node_name}.*",mountpoint="/"}} / node_filesystem_size_bytes{{instance=~".*{node_name}.*",mountpoint="/"}})) * 100'
                result = self._query_prometheus(query)
                if result is not None:
                    return float(result)
            except Exception as e:
                self.logger.debug(f"Prometheus query failed: {e}")
        
        # Fall back to node conditions
        try:
            node = self.k8s_client.get_node_by_name(node_name)
            if node:
                for condition in node.get("conditions", []):
                    if condition.get("type") == "DiskPressure" and condition.get("status") == "True":
                        return 90.0  # Assume high disk usage if under pressure
        except Exception as e:
            self.logger.debug(f"Node condition check failed: {e}")
        
        return 0.0
    
    def _get_cpu_load_ratio(self, node_name: str) -> float:
        """Get CPU load ratio."""
        if self.config.prometheus_url:
            try:
                query = f'node_load1{{instance=~".*{node_name}.*"}} / on(instance) count by (instance) (node_cpu_seconds_total{{mode="idle",instance=~".*{node_name}.*"}})'
                result = self._query_prometheus(query)
                if result is not None:
                    return float(result)
            except Exception as e:
                self.logger.debug(f"Prometheus query failed: {e}")
        
        # Fall back to CPU utilization estimation
        try:
            cpu_util = self._get_cpu_utilization(node_name)
            return cpu_util / 100.0
        except Exception as e:
            self.logger.debug(f"CPU utilization estimation failed: {e}")
            return 0.0
    
    def _query_prometheus(self, query: str) -> Optional[str]:
        """Query Prometheus for metrics."""
        try:
            response = requests.get(
                f"{self.config.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            if data.get("status") == "success" and data.get("data", {}).get("result"):
                return data["data"]["result"][0]["value"][1]
            return None
        except Exception as e:
            self.logger.debug(f"Prometheus query failed: {e}")
            return None
    
    def _get_cpu_utilization_from_metrics_server(self, node_name: str) -> float:
        """Get CPU utilization from Metrics Server."""
        try:
            response = requests.get(
                f"{self.config.metrics_server_url}/nodes/{node_name}",
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            cpu_usage = data.get("usage", {}).get("cpu", "0")
            cpu_capacity = data.get("capacity", {}).get("cpu", "1")
            
            # Convert to numeric values
            cpu_usage_num = self._parse_cpu_value(cpu_usage)
            cpu_capacity_num = self._parse_cpu_value(cpu_capacity)
            
            if cpu_capacity_num > 0:
                return (cpu_usage_num / cpu_capacity_num) * 100
            return 0.0
        except Exception as e:
            self.logger.debug(f"Metrics Server query failed: {e}")
            return 0.0
    
    def _get_memory_utilization_from_metrics_server(self, node_name: str) -> float:
        """Get memory utilization from Metrics Server."""
        try:
            response = requests.get(
                f"{self.config.metrics_server_url}/nodes/{node_name}",
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            memory_usage = data.get("usage", {}).get("memory", "0")
            memory_capacity = data.get("capacity", {}).get("memory", "1")
            
            # Convert to bytes
            memory_usage_bytes = self._parse_memory_value(memory_usage)
            memory_capacity_bytes = self._parse_memory_value(memory_capacity)
            
            if memory_capacity_bytes > 0:
                return (memory_usage_bytes / memory_capacity_bytes) * 100
            return 0.0
        except Exception as e:
            self.logger.debug(f"Metrics Server query failed: {e}")
            return 0.0
    
    def _parse_cpu_value(self, value: str) -> float:
        """Parse CPU value (e.g., '100m' -> 0.1)."""
        if value.endswith('m'):
            return float(value[:-1]) / 1000
        elif value.endswith('n'):
            return float(value[:-1]) / 1000000000
        else:
            return float(value)
    
    def _parse_memory_value(self, value: str) -> int:
        """Parse memory value (e.g., '1Gi' -> 1073741824)."""
        if value.endswith('Ki'):
            return int(float(value[:-2]) * 1024)
        elif value.endswith('Mi'):
            return int(float(value[:-2]) * 1024 * 1024)
        elif value.endswith('Gi'):
            return int(float(value[:-2]) * 1024 * 1024 * 1024)
        elif value.endswith('Ti'):
            return int(float(value[:-2]) * 1024 * 1024 * 1024 * 1024)
        else:
            return int(value)


def load_config() -> NodeGuardianConfig:
    """Load configuration from environment variables."""
    return NodeGuardianConfig(
        namespace=os.getenv("NODEGUARDIAN_NAMESPACE", "nodeguardian-system"),
        metrics_cache_dir=os.getenv("METRICS_CACHE_DIR", "/tmp/nodeguardian/metrics"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        prometheus_url=os.getenv("PROMETHEUS_URL", "http://prometheus-k8s.monitoring.svc:9090"),
        metrics_server_url=os.getenv("METRICS_SERVER_URL", "https://kubernetes.default.svc:443/apis/metrics.k8s.io/v1beta1"),
        alert_email_smtp=os.getenv("ALERT_EMAIL_SMTP", "smtp.gmail.com:587"),
        alert_email_from=os.getenv("ALERT_EMAIL_FROM", "nodeguardian@example.com"),
        alert_email_to=os.getenv("ALERT_EMAIL_TO", "admin@example.com"),
        alert_slack_webhook=os.getenv("ALERT_SLACK_WEBHOOK", ""),
        alert_webhook_url=os.getenv("ALERT_WEBHOOK_URL", ""),
    )
