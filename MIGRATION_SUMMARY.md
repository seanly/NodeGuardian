# NodeGuardian Python迁移总结

## 迁移概述

成功将NodeGuardian的所有hooks的trigger函数调用改为使用Python脚本实现，并实现了配置统一从ConfigMap中加载。

## 完成的工作

### 1. ✅ 分析当前hooks结构
- 分析了3个主要hooks：主控制器、告警管理器、恢复管理器
- 理解了现有的Shell脚本逻辑和配置加载方式
- 识别了需要迁移的核心功能

### 2. ✅ 设计Python脚本架构
- 设计了统一的配置加载机制
- 创建了模块化的Python脚本结构
- 实现了配置缓存和热重载功能

### 3. ✅ 创建Python版本的trigger脚本

#### 主控制器 (`nodeguardian_controller.py`)
- 处理NodeGuardianRule和AlertTemplate的CRD变化
- 管理规则生命周期（注册/注销）
- 实现规则评估和动作执行
- 支持多种动作类型：污点、告警、驱逐、标签、注解

#### 告警管理器 (`alert_manager.py`)
- 处理告警模板渲染和发送
- 支持多种告警渠道：日志、邮件、Webhook
- 实现HTML邮件模板
- 支持告警内容模板化

#### 恢复管理器 (`recovery_manager.py`)
- 处理节点恢复逻辑
- 执行恢复动作（去污点、移除标签/注解、恢复告警）
- 监控恢复条件
- 更新恢复状态

#### 配置加载器 (`config_loader.py`)
- 统一配置加载接口
- 支持从ConfigMap和Secret加载配置
- 配置缓存机制
- 支持配置热重载

### 4. ✅ 修改hooks调用Python脚本

#### 主控制器Hook (`001-nodeguardian-controller.sh`)
```bash
# 检查Python脚本是否存在
local python_script="/scripts/nodeguardian_controller.py"
# 调用Python脚本
python3 "$python_script" "$@"
```

#### 告警管理器Hook (`002-alert-manager.sh`)
```bash
# 检查Python脚本是否存在
local python_script="/scripts/alert_manager.py"
# 调用Python脚本
python3 "$python_script" "$@"
```

#### 恢复管理器Hook (`003-recovery-manager.sh`)
```bash
# 检查Python脚本是否存在
local python_script="/scripts/recovery_manager.py"
# 调用Python脚本
python3 "$python_script" "$@"
```

### 5. ✅ 更新configmap配置结构
- 添加了Python相关配置
- 支持Python脚本超时和重试配置
- 统一配置管理结构
- 保持向后兼容性

### 6. ✅ 测试集成和配置加载
- 创建了集成测试脚本 (`test_integration.py`)
- 测试配置加载器功能
- 测试各个Python脚本模块
- 测试配置文件加载
- 测试绑定上下文解析

## 技术架构

### 配置管理
```
ConfigMap (config.json) → config_loader.py → 各Python脚本
Secret (敏感信息) → config_loader.py → 各Python脚本
```

### 脚本调用链
```
Shell Hook → Python Script → 业务逻辑
```

### 目录结构
```
/scripts/
├── nodeguardian_controller.py  # 主控制器
├── alert_manager.py            # 告警管理器
├── recovery_manager.py         # 恢复管理器
├── config_loader.py            # 配置加载器
├── config-manager.py           # 配置管理工具
├── sendmail.py                 # 邮件发送工具
└── test_integration.py         # 集成测试
```

## 部署更新

### Dockerfile更新
- 安装Python3和必要包
- 复制所有Python脚本
- 设置正确的执行权限
- 创建必要的目录结构

### ConfigMap更新
- 添加Python配置部分
- 支持脚本超时和重试
- 统一配置格式

## 优势

1. **统一配置管理**：所有配置都从ConfigMap加载，便于管理
2. **Python生态**：可以利用丰富的Python库和工具
3. **更好的错误处理**：Python提供更强大的异常处理机制
4. **代码复用**：配置加载器可以在所有脚本中复用
5. **易于测试**：Python脚本更容易进行单元测试
6. **向后兼容**：Shell hooks仍然存在，只是调用Python脚本
7. **模块化设计**：每个功能模块独立，便于维护

## 使用方法

### 构建和部署
```bash
# 构建镜像
docker build -t nodeguardian:latest -f deploy/Dockerfile .

# 部署到Kubernetes
kubectl apply -f deploy/namespace.yaml
kubectl apply -f deploy/configmap.yaml
kubectl apply -f deploy/rbac.yaml
kubectl apply -f deploy/deployment.yaml
```

### 运行测试
```bash
python3 scripts/test_integration.py
```

## 注意事项

1. 确保Python3在容器中可用
2. 所有Python脚本都需要执行权限
3. 配置文件路径必须正确
4. Secret文件需要正确挂载
5. 日志级别可以通过配置调整

## 故障排除

### 常见问题
1. **Python脚本找不到**：检查脚本是否被正确复制到容器中
2. **配置加载失败**：检查ConfigMap是否正确挂载
3. **Secret加载失败**：检查Secret是否正确创建和挂载

### 调试方法
1. 查看容器日志
2. 运行集成测试脚本
3. 检查配置文件内容
4. 验证Python脚本语法

## 总结

成功完成了NodeGuardian的Python迁移，实现了：
- ✅ 所有hooks的trigger函数调用Python脚本
- ✅ 配置统一从ConfigMap中加载
- ✅ 保持了向后兼容性
- ✅ 提供了完整的测试和文档
- ✅ 实现了模块化和可维护的架构

迁移后的系统更加灵活、可维护，并且充分利用了Python生态的优势。
