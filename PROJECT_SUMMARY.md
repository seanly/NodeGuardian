# NodeGuardian 项目总结

## 📋 项目概述

NodeGuardian是一个基于shell-operator的事件驱动Kubernetes节点自愈工具，通过CRD规则引擎实现条件触发、动作执行和智能告警。项目提供了两个实现版本：Shell脚本版本和Python版本。

## 🏗️ 项目结构

```
nodeguardian/
├── crd/                          # CRD定义文件
│   ├── nodeguardianrule-crd.yaml
│   └── alerttemplate-crd.yaml
├── hooks/                        # Shell版本hooks
│   ├── nodeguardian-controller.sh
│   └── alert-manager.sh
├── lib/                          # Shell版本公共库
│   └── common.sh
├── deploy/                       # Shell版本部署配置
│   ├── Dockerfile
│   ├── namespace.yaml
│   ├── rbac.yaml
│   └── deployment.yaml
├── examples/                     # 使用示例
│   ├── high-load-isolation.yaml
│   ├── disk-space-alert.yaml
│   ├── emergency-eviction.yaml
│   └── alert-templates.yaml
├── python-version/               # Python版本
│   ├── src/nodeguardian/         # Python包源码
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── rule_engine.py
│   │   └── alert_manager.py
│   ├── hooks/                    # Python版本hooks
│   │   └── nodeguardian_controller.py
│   ├── deploy/                   # Python版本部署配置
│   │   ├── Dockerfile
│   │   └── deployment.yaml
│   ├── tests/                    # 测试文件
│   │   └── test_rule_engine.py
│   ├── pyproject.toml           # Python项目配置
│   ├── deploy.sh                # Python版本部署脚本
│   └── README.md                # Python版本文档
├── deploy.sh                    # Shell版本部署脚本
├── README.md                    # 主文档
└── PROJECT_SUMMARY.md           # 项目总结
```

## 🚀 核心功能

### 1. 规则引擎
- **条件评估**：支持多条件组合（AND/OR逻辑）
- **指标监控**：CPU、内存、磁盘使用率，CPU负载率
- **操作符支持**：大于、小于、等于、不等于、大于等于、小于等于
- **持续时间**：支持条件持续时间判断
- **冷却期**：避免频繁触发相同动作

### 2. 动作执行
- **污点管理**：添加/移除节点污点
- **Pod驱逐**：智能驱逐Pod释放资源
- **标签管理**：添加/移除节点标签
- **注解管理**：添加/移除节点注解
- **告警发送**：多渠道告警通知

### 3. 告警系统
- **多渠道支持**：日志、Webhook、邮件
- **模板化**：支持Jinja2模板渲染
- **变量替换**：动态替换告警内容
- **默认模板**：提供常用告警模板

### 4. 监控集成
- **Prometheus**：从Prometheus获取指标数据
- **Metrics Server**：从Kubernetes Metrics Server获取基础指标
- **多源支持**：支持多种指标数据源

## 🔧 技术实现

### Shell版本特点
- **轻量级**：基于shell脚本，资源占用少
- **简单部署**：无需额外依赖
- **快速开发**：使用熟悉的shell命令
- **易于调试**：日志输出清晰

### Python版本特点
- **类型安全**：使用Pydantic和类型注解
- **结构化日志**：使用structlog提供结构化日志
- **异步支持**：支持异步操作提高性能
- **易于扩展**：面向对象设计，便于功能扩展
- **测试友好**：完整的测试框架

## 📊 架构设计

### 事件驱动架构
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ NodeGuardianRule│    │   Controller     │    │   Node Metrics  │
│     CRD         │───▶│   (Python/Shell) │◀───│  (Prometheus)   │
└─────────────────┘    └─────────┬────────┘    └─────────────────┘
         │                       │                       │
         │ 事件监听               │ 定期轮询               │
         │ (ADDED/MODIFIED)      │ (checkInterval)       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Rule Manager   │    │  Timer Manager   │    │ Metrics Collector│
│  - 规则注册     │    │  - 定时器管理    │    │  - 指标获取     │
│  - 规则更新     │    │  - 间隔控制      │    │  - 数据缓存     │
│  - 规则删除     │    │  - 并发控制      │    │  - 错误处理     │
└─────────┬───────┘    └─────────┬────────┘    └─────────┬───────┘
          │                      │                       │
          └──────────────────────┼───────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │    Rule Engine          │
                    │  - 条件评估             │
                    │  - 动作执行             │
                    │  - 状态管理             │
                    │  - 冷却期控制           │
                    └─────────┬───────────────┘
                              │
                              ▼
                    ┌─────────────────────────┐
                    │    Action Executors     │
                    │  - Taint Manager        │
                    │  - Alert Manager        │
                    │  - Eviction Manager     │
                    │  - Recovery Manager     │
                    └─────────────────────────┘
```

### 数据流
1. **事件监听**：shell-operator监听CRD变化
2. **规则注册**：新规则创建时注册到规则引擎
3. **定期检查**：按配置间隔定期检查节点指标
4. **条件评估**：评估节点是否满足规则条件
5. **动作执行**：满足条件时执行相应动作
6. **状态更新**：更新CRD状态和告警通知

## 🎯 使用场景

### 1. 高负载节点隔离
- 监控CPU和内存使用率
- 自动添加污点防止新Pod调度
- 发送告警通知运维人员

### 2. 磁盘空间告警
- 监控磁盘使用率
- 提前告警避免磁盘满
- 自动清理临时文件

### 3. 紧急资源释放
- 监控内存使用率
- 自动驱逐部分Pod
- 添加NoExecute污点

### 4. 节点状态管理
- 自动添加状态标签
- 记录触发时间
- 支持自动恢复

## 🔍 监控和运维

### 日志监控
- 结构化日志输出
- 支持不同日志级别
- 便于日志分析和告警

### 指标监控
- 规则执行统计
- 检查成功率
- 平均响应时间

### 状态管理
- CRD状态字段
- 触发历史记录
- 错误信息记录

## 🚀 部署方式

### 快速部署
```bash
# Shell版本
./deploy.sh --full

# Python版本
cd python-version
./deploy.sh --full
```

### 生产部署
1. 配置镜像仓库
2. 设置告警渠道
3. 调整资源限制
4. 配置监控指标

## 🔧 配置管理

### 环境变量
- 命名空间配置
- 日志级别设置
- 指标源配置
- 告警渠道配置

### CRD配置
- 规则定义
- 告警模板
- 监控间隔
- 冷却期设置

## 🧪 测试策略

### 单元测试
- 规则引擎测试
- 条件评估测试
- 动作执行测试

### 集成测试
- 端到端测试
- 告警发送测试
- 指标收集测试

### 性能测试
- 大量规则测试
- 高并发测试
- 资源使用测试

## 🔄 扩展性

### 功能扩展
- 新增指标类型
- 新增动作类型
- 新增告警渠道

### 性能扩展
- 水平扩展支持
- 缓存优化
- 异步处理

### 集成扩展
- 更多监控系统
- 更多告警渠道
- 更多云平台

## 📈 未来规划

### 短期目标
- 完善测试覆盖
- 优化性能
- 增加监控指标

### 中期目标
- 支持更多指标类型
- 增加机器学习能力
- 支持多集群管理

### 长期目标
- 成为标准化的节点自愈解决方案
- 支持更多云平台
- 提供SaaS服务

## 🤝 贡献指南

### 开发环境
- 安装必要的开发工具
- 配置测试环境
- 遵循代码规范

### 提交流程
- Fork项目
- 创建特性分支
- 编写测试
- 提交PR

### 代码规范
- Shell版本：遵循Shell最佳实践
- Python版本：遵循PEP 8规范
- 文档：保持文档同步更新

## 📄 许可证

本项目采用Apache License 2.0许可证，允许商业使用和修改。

## 🙏 致谢

感谢以下开源项目的支持：
- [shell-operator](https://github.com/flant/shell-operator)
- [Kubernetes](https://kubernetes.io/)
- [Prometheus](https://prometheus.io/)
- [Python](https://python.org/)
- [uv](https://github.com/astral-sh/uv)
