"""Tests for NodeGuardian rule engine."""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from nodeguardian.rule_engine import RuleEngine, Rule, Condition
from nodeguardian.common import NodeGuardianConfig


@pytest.fixture
def config():
    """Create test configuration."""
    return NodeGuardianConfig(
        namespace="test-namespace",
        log_level="DEBUG"
    )


@pytest.fixture
def rule_engine(config):
    """Create test rule engine."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config.metrics_cache_dir = temp_dir
        engine = RuleEngine(config)
        engine.rules_dir = temp_dir
        engine.cooldown_dir = temp_dir
        yield engine


@pytest.fixture
def sample_rule_data():
    """Sample rule data for testing."""
    return {
        "metadata": {"name": "test-rule"},
        "spec": {
            "conditions": [
                {
                    "metric": "cpuUtilizationPercent",
                    "operator": "GreaterThan",
                    "value": 80,
                    "duration": "5m",
                    "description": "CPU usage too high"
                }
            ],
            "conditionLogic": "AND",
            "nodeSelector": {
                "matchLabels": {
                    "node-role.kubernetes.io/worker": "true"
                }
            },
            "actions": [
                {
                    "type": "taint",
                    "taint": {
                        "key": "nodeguardian/test",
                        "value": "true",
                        "effect": "NoSchedule"
                    }
                }
            ],
            "recoveryConditions": [],
            "recoveryActions": [],
            "monitoring": {
                "checkInterval": "60s",
                "cooldownPeriod": "5m"
            },
            "metadata": {
                "priority": 100,
                "enabled": True,
                "description": "Test rule"
            }
        }
    }


def test_load_rule(rule_engine, sample_rule_data):
    """Test loading a rule from data."""
    rule = rule_engine.load_rule(sample_rule_data)
    
    assert rule.name == "test-rule"
    assert len(rule.conditions) == 1
    assert rule.conditions[0].metric == "cpuUtilizationPercent"
    assert rule.conditions[0].operator == "GreaterThan"
    assert rule.conditions[0].value == 80
    assert rule.condition_logic == "AND"
    assert rule.enabled is True


def test_save_and_load_rule(rule_engine, sample_rule_data):
    """Test saving and loading a rule."""
    rule = rule_engine.load_rule(sample_rule_data)
    rule_engine.save_rule(rule)
    
    loaded_rule = rule_engine.load_rule_from_file("test-rule")
    assert loaded_rule is not None
    assert loaded_rule.name == "test-rule"
    assert len(loaded_rule.conditions) == 1


def test_evaluate_condition():
    """Test condition evaluation."""
    condition = Condition(
        metric="cpuUtilizationPercent",
        operator="GreaterThan",
        value=80.0
    )
    
    # Mock metrics collector
    with patch('nodeguardian.rule_engine.MetricsCollector') as mock_collector:
        mock_instance = Mock()
        mock_instance.get_node_metrics.return_value = 85.0
        mock_collector.return_value = mock_instance
        
        engine = RuleEngine(NodeGuardianConfig())
        result = engine.evaluate_condition(condition, "test-node")
        
        assert result is True


def test_evaluate_condition_false():
    """Test condition evaluation when condition is not met."""
    condition = Condition(
        metric="cpuUtilizationPercent",
        operator="GreaterThan",
        value=80.0
    )
    
    # Mock metrics collector
    with patch('nodeguardian.rule_engine.MetricsCollector') as mock_collector:
        mock_instance = Mock()
        mock_instance.get_node_metrics.return_value = 70.0
        mock_collector.return_value = mock_instance
        
        engine = RuleEngine(NodeGuardianConfig())
        result = engine.evaluate_condition(condition, "test-node")
        
        assert result is False


def test_parse_duration():
    """Test duration parsing."""
    engine = RuleEngine(NodeGuardianConfig())
    
    assert engine._parse_duration("30s") == 30
    assert engine._parse_duration("5m") == 300
    assert engine._parse_duration("2h") == 7200
    assert engine._parse_duration("1d") == 86400


def test_get_matching_nodes(rule_engine):
    """Test getting matching nodes."""
    node_selector = {
        "matchLabels": {
            "node-role.kubernetes.io/worker": "true"
        }
    }
    
    # Mock Kubernetes client
    with patch.object(rule_engine.k8s_client, 'get_nodes') as mock_get_nodes:
        mock_get_nodes.return_value = [
            {"name": "worker-1"},
            {"name": "worker-2"}
        ]
        
        nodes = rule_engine.get_matching_nodes(node_selector)
        assert len(nodes) == 2
        assert "worker-1" in nodes
        assert "worker-2" in nodes


def test_get_matching_nodes_by_name(rule_engine):
    """Test getting matching nodes by name."""
    node_selector = {
        "nodeNames": ["node-1", "node-2"]
    }
    
    nodes = rule_engine.get_matching_nodes(node_selector)
    assert nodes == ["node-1", "node-2"]


def test_cooldown_mechanism(rule_engine):
    """Test cooldown mechanism."""
    rule_name = "test-rule"
    node_name = "test-node"
    
    # Initially not in cooldown
    assert not rule_engine.is_in_cooldown(rule_name, node_name)
    
    # Set cooldown
    rule_engine.set_cooldown(rule_name, node_name)
    
    # Should be in cooldown
    assert rule_engine.is_in_cooldown(rule_name, node_name)


def test_delete_rule(rule_engine, sample_rule_data):
    """Test deleting a rule."""
    rule = rule_engine.load_rule(sample_rule_data)
    rule_engine.save_rule(rule)
    
    # Rule should exist
    assert rule_engine.load_rule_from_file("test-rule") is not None
    
    # Delete rule
    rule_engine.delete_rule("test-rule")
    
    # Rule should not exist
    assert rule_engine.load_rule_from_file("test-rule") is None


if __name__ == "__main__":
    pytest.main([__file__])
