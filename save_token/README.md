# Save-Token 项目重构需求文档

## 一、项目概述

本项目旨在重构 DeekSeek-tui，实现一个基于 **Save-Token 核心宗旨** 的任务处理系统。系统通过递归任务拆分、多子代理并行执行、结果合并与测试验证的方式，以最高效的 Token 利用方式完成各类用户需求。

**现有实现状态**：项目已完成 Python 版本的核心功能，支持 DeepSeek、腾讯元宝、Kimi、豆包等多个 AI 提供商，通过 OpenCLI 浏览器自动化实现无 API Key 访问。

---

## 二、核心宗旨

系统需始终遵循"**省Token**"核心宗旨执行所有任务，即所有任务必须经过 Save-Token 机制处理，确保以最小的 Token 消耗完成任务目标。

| 原则 | 说明 |
|------|------|
| **优先使用免费资源** | 优先调用免费 AI 网页服务，避免使用付费 API |
| **任务拆分优化** | 将复杂任务拆分为原子任务，最大化 Token 利用率 |
| **智能重试机制** | 失败自动重试，优化请求策略 |

---

## 三、系统架构

### 3.1 任务处理流程

```
用户输入 → 任务分析 → 任务拆分 → 并行执行 → 结果合并 → 测试验证 → 输出结果
     ↓                                      ↓
  历史上下文                              失败回滚
```

**详细流程**：
1. **接收用户问题及上下文**
2. **将任务拆分为若干步骤**
3. **启用多个子代理并行处理子任务**
4. **递归拆分直至所有任务均为原子性任务**
5. **等待所有子任务完成**
6. **合并子任务结果**
7. **测试代码结果**
8. **测试成功则应用新版本，失败则回滚至旧版本**

### 3.2 原子性任务定义

| 任务类型 | 示例 | 准确率要求 |
|---------|------|-----------|
| **简单计算任务** | "1+2 = ？" | 99.99% |
| **基础代码编写** | "使用python帮我写个快排" | 99.99% |
| **图片生成任务** | "帮我生成一张图片，风格是..." | 99.99% |
| **文件操作任务** | "按我上传的几个文档操作" | 99.99% |
| **代码错误检查** | "帮我检查代码错误" | 99.99% |

### 3.3 技术栈选型

| 层次 | 技术 | 职责 | 稳定性要求 |
|------|------|------|-----------|
| **核心引擎** | Python | 任务分发、代理管理、结果合并、测试验证 | 稳定 |
| **提供商实现** | Python | 各 AI 厂家网页交互、问题发送、结果提取 | 动态更新 |
| **浏览器桥接** | Python + OpenCLI | 浏览器自动化操作 | 稳定 |
| **命令行接口** | Python + Click | CLI 命令实现 | 稳定 |

> **架构说明**：当前实现采用纯 Python 架构，已具备良好的扩展性。原需求中提到的 Rust 核心架构可作为后续性能优化方向。

### 3.4 模块架构

```
save_token/
├── cli.py              # CLI 入口（st / save-token 命令）
├── core.py             # 核心引擎（ask() 调用、重试逻辑）
├── opencli_bridge.py   # OpenCLI 浏览器桥接
├── options.py          # 请求选项定义
├── config/
│   └── manager.py      # 配置管理
└── providers/
    ├── base.py         # 基础 Provider 接口
    ├── registry.py     # Provider 注册发现
    ├── deepseek.py     # DeepSeek 实现
    ├── yuanbao.py      # 腾讯元宝实现
    ├── kimi.py         # Kimi 实现
    └── doubao.py       # 豆包实现
```

---

## 四、核心功能设计

### 4.1 CLI 命令接口

| 命令 | 子命令 | 参数 | 功能说明 |
|------|--------|------|---------|
| `st` | `ask` | `-p`, `-r`, `-t`, `--deep-think`, `--web-search`, `-j` | 向 AI 提问 |
| `st` | `providers` | 无 | 列出可用提供商 |
| `st` | `config show` | 无 | 显示配置 |
| `st` | `config set` | `key`, `value` | 设置配置项 |
| `st` | `config path` | 无 | 显示配置文件路径 |

### 4.2 Provider 接口规范

**基础类定义**（base.py）：

```python
class BaseProvider:
    def ask(self, question: str, options: AskOptions) -> AskResult:
        """发送问题并返回答案"""
    
class ProviderConfig:
    name: str                    # 提供商名称
    url: str                     # 聊天页面 URL
    input_selector: str          # 输入框选择器
    send_selector: str           # 发送按钮选择器
    send_method: str             # 发送方式 ("enter" / "click")
    response_js: str             # 提取答案的 JS 脚本
    thinking_js: str             # 提取思考过程的 JS 脚本
    needs_fill_not_type: bool    # 是否需要 fill() 而非 type()
    post_send_wait: int          # 发送后等待时间(秒)
    session_name: str            # 浏览器会话名称
```

### 4.3 配置管理

**配置文件结构**：
```toml
[provider]
  [provider.default]
    name = "deepseek"
  
  [provider.deepseek]
    url = "https://chat.deepseek.com/"
  
  [provider.yuanbao]
    url = "https://yuanbao.tencent.com/chat"
  
  [provider.kimi]
    url = "https://kimi.moonshot.cn/"
  
  [provider.doubao]
    url = "https://www.doubao.com/chat/"
```

---

## 五、实施计划

### 5.1 当前已完成功能

| 阶段 | 状态 | 完成内容 |
|------|------|---------|
| **基础架构** | ✅ 完成 | CLI 命令、核心引擎、配置管理 |
| **OpenCLI 桥接** | ✅ 完成 | 浏览器自动化封装 |
| **Provider 框架** | ✅ 完成 | 基础接口、注册机制 |
| **DeepSeek 集成** | ✅ 完成 | 支持 deep_think、web_search 切换 |
| **元宝集成** | ✅ 完成 | 支持 Quill 编辑器输入 |
| **Kimi 集成** | ✅ 完成 | 支持 contenteditable 输入 |
| **豆包集成** | ✅ 完成 | 支持 textarea 输入 |

### 5.2 待扩展功能

| 优先级 | 功能 | 描述 |
|--------|------|------|
| **高** | 任务拆分引擎 | 实现复杂任务递归拆分 |
| **高** | 并行执行框架 | 多 Provider 并行调用 |
| **中** | 结果合并机制 | 智能合并多个子任务结果 |
| **中** | 版本控制 | 代码测试与回滚机制 |
| **低** | Rust 核心 | 性能敏感部分迁移至 Rust |

---

## 六、示例流程

以用户需求"帮我实现使用OpenCli实现Save-Token这个项目，支持[deepseek,元宝，kimi，豆包]"为例：

1. **接收用户需求** → 解析为多提供商集成任务
2. **任务规划** → 识别需要实现4个 Provider
3. **并行执行** → 分别实现 deepseek、yuanbao、kimi、doubao Provider
4. **结果合并** → 统一注册到 Provider Registry
5. **测试验证** → 各 Provider 分别测试
6. **版本应用** → 发布新版本

---

## 七、质量要求

| 指标 | 目标 | 当前状态 |
|------|------|---------|
| **任务拆分准确率** | ≥99% | 待实现 |
| **原子任务成功率** | ≥99.99% | 待验证 |
| **Token 效率提升** | ≥50% | 待评估 |
| **代码可维护性** | 遵循最佳实践 | ✅ 良好 |
| **错误处理** | 完善的异常处理 | ✅ 已实现重试机制 |
| **日志记录** | 完整的操作日志 | ✅ 已实现 |

---

## 八、后续扩展

### 8.1 AI 提供商扩展

完成现有集成验证稳定后，逐步扩展至其他 AI 厂家：

| 厂家 | 状态 | 备注 |
|------|------|------|
| DeepSeek | ✅ 已集成 | 支持深度思考、智能搜索切换 |
| 腾讯元宝 | ✅ 已集成 | 支持 Quill 编辑器 |
| Kimi | ✅ 已集成 | 支持长文本输入 |
| 豆包 | ✅ 已集成 | 字节跳动旗下 |
| 智谱清言 | ⏳ 待集成 | 支持代码解释 |
| 讯飞星火 | ⏳ 待集成 | 语音能力强 |

### 8.2 功能扩展路线图

| 阶段 | 功能 | 时间预估 |
|------|------|---------|
| Phase 1 | 任务拆分引擎 | 2周 |
| Phase 2 | 并行执行框架 | 2周 |
| Phase 3 | 结果合并与测试 | 2周 |
| Phase 4 | Rust 核心重构 | 4周 |

---

## 九、代码规范

### 9.1 Provider 实现规范

1. **命名规范**：文件名为提供商英文小写（如 `deepseek.py`）
2. **类名**：统一使用 `Provider` 类名
3. **配置**：必须定义 `PROVIDER_CONFIG` 常量
4. **继承**：必须继承 `BaseProvider`
5. **日志**：使用 `logging.getLogger(__name__)` 记录日志

### 9.2 错误处理规范

1. **重试机制**：核心引擎统一处理重试（默认 2 次）
2. **异常类型**：使用 `RuntimeError` 表示操作失败
3. **错误信息**：包含上下文信息便于排查

---

## 十、部署与安装

### 10.1 依赖要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | ≥3.10 | 运行环境 |
| click | ≥8.0 | CLI 框架 |
| tomli | ≥2.0 | TOML 配置解析 |
| opencli | 最新 | 浏览器自动化 |

### 10.2 安装方式

```bash
# 安装包
pip install save-token

# 开发模式
pip install -e .

# 安装 OpenCLI
npm install -g opencli
```

### 10.3 运行命令

```bash
# 基本使用
st ask "用Python写一个快排"

# 指定提供商
st ask "什么是Rust的所有权" -p deepseek

# JSON 输出
st ask "今天天气怎么样" -j

# 启用深度思考
st ask "复杂问题分析" -p deepseek --deep-think
```

---

## 十一、安全考虑

| 风险点 | 解决方案 |
|--------|---------|
| **Cookie 安全** | 使用独立浏览器会话，避免污染用户数据 |
| **输入注入** | 对用户输入进行适当转义处理 |
| **超时保护** | 每个操作设置超时时间（默认 30 秒） |
| **日志脱敏** | 日志中不记录敏感信息 |

---

## 十二、附录

### A. Provider 注册机制

通过 `registry.py` 实现自动发现：

1. 扫描 `providers/` 目录下所有模块
2. 查找包含 `PROVIDER_CONFIG` 和 `Provider` 的模块
3. 自动注册到全局 Provider 字典

### B. OpenCLI 桥接层

`opencli_bridge.py` 封装所有浏览器操作：

- `fill()`: 填充输入框
- `click()`: 点击元素
- `eval()`: 执行 JavaScript
- `keys()`: 发送键盘事件
- `navigate_and_wait()`: 导航并等待页面加载
