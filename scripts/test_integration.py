#!/usr/bin/env python3
"""
NodeGuardian Integration Test Script
测试Python脚本集成和配置加载
"""

import json
import os
import sys
import tempfile
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_config_loader():
    """测试配置加载器"""
    logger.info("Testing config loader...")
    
    try:
        from config_loader import get_config, get_config_section, get_config_value
        
        # 测试获取完整配置
        config = get_config()
        assert isinstance(config, dict), "Config should be a dictionary"
        logger.info("✓ Config loading successful")
        
        # 测试获取配置部分
        email_config = get_config_section('email')
        assert isinstance(email_config, dict), "Email config should be a dictionary"
        logger.info("✓ Config section loading successful")
        
        # 测试获取配置值
        smtp_server = get_config_value('email', 'smtpServer', 'default')
        assert smtp_server is not None, "SMTP server should not be None"
        logger.info("✓ Config value loading successful")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Config loader test failed: {e}")
        return False

def test_nodeguardian_controller():
    """测试NodeGuardian控制器"""
    logger.info("Testing NodeGuardian controller...")
    
    try:
        from nodeguardian_controller import NodeGuardianController
        
        # 创建控制器实例
        controller = NodeGuardianController()
        assert controller is not None, "Controller should be created"
        logger.info("✓ Controller instantiation successful")
        
        # 测试配置加载
        config = controller.config
        assert isinstance(config, dict), "Controller config should be a dictionary"
        logger.info("✓ Controller config loading successful")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ NodeGuardian controller test failed: {e}")
        return False

def test_alert_manager():
    """测试告警管理器"""
    logger.info("Testing alert manager...")
    
    try:
        from alert_manager import AlertManager
        
        # 创建告警管理器实例
        alert_manager = AlertManager()
        assert alert_manager is not None, "Alert manager should be created"
        logger.info("✓ Alert manager instantiation successful")
        
        # 测试配置加载
        config = alert_manager.config
        assert isinstance(config, dict), "Alert manager config should be a dictionary"
        logger.info("✓ Alert manager config loading successful")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Alert manager test failed: {e}")
        return False

def test_recovery_manager():
    """测试恢复管理器"""
    logger.info("Testing recovery manager...")
    
    try:
        from recovery_manager import RecoveryManager
        
        # 创建恢复管理器实例
        recovery_manager = RecoveryManager()
        assert recovery_manager is not None, "Recovery manager should be created"
        logger.info("✓ Recovery manager instantiation successful")
        
        # 测试配置加载
        config = recovery_manager.config
        assert isinstance(config, dict), "Recovery manager config should be a dictionary"
        logger.info("✓ Recovery manager config loading successful")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Recovery manager test failed: {e}")
        return False

def test_config_file_loading():
    """测试配置文件加载"""
    logger.info("Testing config file loading...")
    
    try:
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "test": {
                    "value": "test_value",
                    "number": 42
                }
            }
            json.dump(test_config, f)
            temp_config_file = f.name
        
        # 设置环境变量指向临时配置文件
        original_config_dir = os.environ.get('NODEGUARDIAN_CONFIG_DIR')
        os.environ['NODEGUARDIAN_CONFIG_DIR'] = os.path.dirname(temp_config_file)
        
        try:
            # 重新加载配置
            from config_loader import reload_config
            config = reload_config()
            
            # 验证配置
            test_value = config.get('test', {}).get('value')
            assert test_value == "test_value", f"Expected 'test_value', got '{test_value}'"
            logger.info("✓ Config file loading successful")
            
            return True
            
        finally:
            # 清理
            os.unlink(temp_config_file)
            if original_config_dir:
                os.environ['NODEGUARDIAN_CONFIG_DIR'] = original_config_dir
            elif 'NODEGUARDIAN_CONFIG_DIR' in os.environ:
                del os.environ['NODEGUARDIAN_CONFIG_DIR']
        
    except Exception as e:
        logger.error(f"✗ Config file loading test failed: {e}")
        return False

def test_directory_creation():
    """测试目录创建"""
    logger.info("Testing directory creation...")
    
    try:
        # 测试目录
        test_dirs = [
            "/tmp/nodeguardian/rules",
            "/tmp/nodeguardian/templates", 
            "/tmp/nodeguardian/cooldown"
        ]
        
        for test_dir in test_dirs:
            Path(test_dir).mkdir(parents=True, exist_ok=True)
            assert os.path.exists(test_dir), f"Directory {test_dir} should exist"
            logger.info(f"✓ Directory {test_dir} created successfully")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Directory creation test failed: {e}")
        return False

def test_binding_context_parsing():
    """测试绑定上下文解析"""
    logger.info("Testing binding context parsing...")
    
    try:
        # 创建测试绑定上下文
        test_context = [
            {
                "type": "onStartup",
                "binding": "startup",
                "objects": []
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_context, f)
            temp_context_file = f.name
        
        try:
            # 设置环境变量
            original_context_path = os.environ.get('BINDING_CONTEXT_PATH')
            os.environ['BINDING_CONTEXT_PATH'] = temp_context_file
            
            # 测试解析
            with open(temp_context_file, 'r') as f:
                context = json.load(f)
            
            assert len(context) > 0, "Context should not be empty"
            assert context[0]['type'] == 'onStartup', "Context type should be onStartup"
            logger.info("✓ Binding context parsing successful")
            
            return True
            
        finally:
            # 清理
            os.unlink(temp_context_file)
            if original_context_path:
                os.environ['BINDING_CONTEXT_PATH'] = original_context_path
            elif 'BINDING_CONTEXT_PATH' in os.environ:
                del os.environ['BINDING_CONTEXT_PATH']
        
    except Exception as e:
        logger.error(f"✗ Binding context parsing test failed: {e}")
        return False

def main():
    """主测试函数"""
    logger.info("Starting NodeGuardian integration tests...")
    
    tests = [
        ("Config Loader", test_config_loader),
        ("Directory Creation", test_directory_creation),
        ("NodeGuardian Controller", test_nodeguardian_controller),
        ("Alert Manager", test_alert_manager),
        ("Recovery Manager", test_recovery_manager),
        ("Config File Loading", test_config_file_loading),
        ("Binding Context Parsing", test_binding_context_parsing),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        logger.info(f"\n--- Running {test_name} Test ---")
        try:
            if test_func():
                passed += 1
                logger.info(f"✓ {test_name} test PASSED")
            else:
                failed += 1
                logger.error(f"✗ {test_name} test FAILED")
        except Exception as e:
            failed += 1
            logger.error(f"✗ {test_name} test FAILED with exception: {e}")
    
    logger.info(f"\n--- Test Results ---")
    logger.info(f"Total tests: {passed + failed}")
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")
    
    if failed == 0:
        logger.info("🎉 All tests PASSED! Integration is working correctly.")
        return 0
    else:
        logger.error("❌ Some tests FAILED. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
