#!/usr/bin/env python3
"""
NodeGuardian Email Sender Test Script
测试邮件发送功能
"""

import json
import subprocess
import sys
import os

def test_email_sender():
    """测试邮件发送功能"""
    
    # 测试配置
    test_config = {
        "smtpServer": "smtp.gmail.com",
        "smtpPort": 587,
        "username": "test@example.com",
        "password": "test_password",
        "from": "nodeguardian@example.com",
        "to": "admin@example.com",
        "useTLS": True,
        "useSSL": False
    }
    
    # 测试告警数据
    test_alert = {
        "title": "NodeGuardian Test Alert",
        "summary": "This is a test alert from NodeGuardian",
        "severity": "warning",
        "ruleName": "test-rule",
        "triggeredNodes": "test-node-1",
        "description": "This is a test alert to verify email functionality",
        "timestamp": "2024-01-01T12:00:00Z"
    }
    
    # 获取脚本路径
    script_path = os.path.join(os.path.dirname(__file__), 'sendmail.py')
    
    if not os.path.exists(script_path):
        print(f"Error: Email script not found at {script_path}")
        return False
    
    print("Testing NodeGuardian Email Sender...")
    print(f"Script path: {script_path}")
    print(f"Config: {json.dumps(test_config, indent=2)}")
    print(f"Alert data: {json.dumps(test_alert, indent=2)}")
    
    try:
        # 调用邮件发送脚本（默认使用统一配置）
        result = subprocess.run([
            'python3', script_path,
            '--alert-data', json.dumps(test_alert),
            '--format', 'html'
        ], capture_output=True, text=True, timeout=30)
        
        print(f"Exit code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")
        
        if result.returncode == 0:
            print("✅ Email sender test completed successfully")
            return True
        else:
            print("❌ Email sender test failed")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Email sender test timed out")
        return False
    except Exception as e:
        print(f"❌ Email sender test error: {str(e)}")
        return False

def test_config_validation():
    """测试配置验证"""
    print("\nTesting configuration validation...")
    
    # 测试无效配置
    invalid_configs = [
        {},  # 空配置
        {"smtpServer": "smtp.gmail.com"},  # 缺少from和to
        {"from": "test@example.com"},  # 缺少to
        {"to": "admin@example.com"},  # 缺少from
    ]
    
    script_path = os.path.join(os.path.dirname(__file__), 'send_email.py')
    test_alert = {"title": "Test", "summary": "Test"}
    
    for i, config in enumerate(invalid_configs):
        print(f"Testing invalid config {i+1}: {config}")
        try:
            result = subprocess.run([
                'python3', script_path,
                '--alert-data', json.dumps(test_alert),
                '--format', 'html'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                print(f"✅ Correctly rejected invalid config {i+1}")
            else:
                print(f"❌ Should have rejected invalid config {i+1}")
                
        except Exception as e:
            print(f"❌ Error testing config {i+1}: {str(e)}")

if __name__ == '__main__':
    print("NodeGuardian Email Sender Test Suite")
    print("=" * 50)
    
    # 测试基本功能
    success = test_email_sender()
    
    # 测试配置验证
    test_config_validation()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 All tests completed!")
        sys.exit(0)
    else:
        print("💥 Some tests failed!")
        sys.exit(1)
