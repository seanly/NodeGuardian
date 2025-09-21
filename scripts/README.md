# NodeGuardian Scripts

这个目录包含了NodeGuardian的辅助脚本。

## 邮件发送脚本

### sendmail.py

NodeGuardian的邮件发送脚本，支持通过SMTP发送HTML格式的告警邮件。

#### 功能特性

- 支持SMTP/SSL/TLS连接
- HTML格式邮件模板
- 灵活的配置选项
- 错误处理和日志记录
- 支持多收件人

#### 使用方法

```bash
# 使用统一配置（默认方式）
python3 sendmail.py --alert-data '{"title":"Test Alert","summary":"Test message","severity":"warning"}' --format html

# 使用自定义配置（覆盖统一配置）
python3 sendmail.py --config '{"smtpServer":"smtp.gmail.com","smtpPort":587,"username":"user@example.com","password":"password","from":"alerts@example.com","to":"admin@example.com"}' --alert-data '{"title":"Test Alert","summary":"Test message","severity":"warning"}' --format html
```

#### 参数说明

- `--config`: 邮件配置JSON字符串（可选，提供时覆盖统一配置）
- `--alert-data`: 告警数据JSON字符串  
- `--format`: 邮件格式 (html/text，默认html)

#### 配置参数

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| smtpServer | string | 是 | SMTP服务器地址 |
| smtpPort | integer | 否 | SMTP端口 (默认587) |
| username | string | 否 | SMTP用户名 |
| password | string | 否 | SMTP密码 |
| from | string | 是 | 发件人邮箱 |
| to | string/array | 是 | 收件人邮箱 |
| useTLS | boolean | 否 | 使用TLS (默认true) |
| useSSL | boolean | 否 | 使用SSL (默认false) |

#### 告警数据格式

```json
{
  "title": "告警标题",
  "summary": "告警摘要", 
  "severity": "critical|error|warning|info",
  "ruleName": "规则名称",
  "triggeredNodes": "触发节点",
  "description": "详细描述",
  "timestamp": "时间戳"
}
```

#### 环境变量配置

在Kubernetes部署中，可以通过以下环境变量配置邮件：

```yaml
env:
- name: ALERT_EMAIL_SMTP
  value: "smtp.gmail.com:587"
- name: ALERT_EMAIL_FROM  
  value: "nodeguardian@example.com"
- name: ALERT_EMAIL_TO
  value: "admin@example.com"
- name: ALERT_EMAIL_USERNAME
  value: "your-username"
- name: ALERT_EMAIL_PASSWORD
  value: "your-password"
```

#### 常见SMTP配置

**Gmail:**
```json
{
  "smtpServer": "smtp.gmail.com",
  "smtpPort": 587,
  "useTLS": true,
  "useSSL": false
}
```

**Outlook/Hotmail:**
```json
{
  "smtpServer": "smtp-mail.outlook.com", 
  "smtpPort": 587,
  "useTLS": true,
  "useSSL": false
}
```

**企业邮箱:**
```json
{
  "smtpServer": "mail.company.com",
  "smtpPort": 465,
  "useTLS": false,
  "useSSL": true
}
```

### test_email.py

邮件发送功能的测试脚本。

#### 使用方法

```bash
python3 test_email.py
```

测试脚本会：
- 验证邮件发送脚本的基本功能
- 测试配置验证逻辑
- 检查错误处理

## 集成说明

邮件发送功能已集成到NodeGuardian的告警管理器中：

1. **Hook集成**: `002-alert-manager.sh` 中的 `hook::send_to_email()` 函数
2. **Docker集成**: Dockerfile中已安装Python3并复制脚本
3. **统一配置集成**: 默认从统一配置文件自动加载邮件配置
4. **配置覆盖**: 支持通过命令行参数覆盖统一配置

## 故障排除

### 常见问题

1. **连接超时**
   - 检查SMTP服务器地址和端口
   - 确认网络连接正常

2. **认证失败**
   - 检查用户名和密码
   - 确认邮箱支持SMTP认证

3. **权限错误**
   - 确保脚本有执行权限
   - 检查Python3是否可用

4. **配置错误**
   - 验证JSON格式正确
   - 检查必需参数是否提供

### 调试模式

启用详细日志：

```bash
export PYTHONPATH=/scripts
python3 -c "import logging; logging.basicConfig(level=logging.DEBUG)"
python3 send_email.py --config '...' --alert-data '...'
```

## 安全注意事项

1. **密码安全**: 不要在配置文件中明文存储密码
2. **TLS/SSL**: 生产环境建议使用加密连接
3. **权限控制**: 限制脚本的执行权限
4. **网络安全**: 确保SMTP端口访问安全
