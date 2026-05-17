# Save-Token

**用免费 AI 替代付费 API Token 的命令行工具。**

通过浏览器自动化（OpenCLI）操控 DeepSeek、元宝、Kimi 等免费 AI 聊天页面，无需 API Key。

## 快速开始

```bash
# 安装
pip install -e .

# 单次提问
st ask "用 Python 写一个快排"

# 多任务流水线 — 同一 Chat 逐轮对话，上下文保持
st run "1. 什么是闭包 2. 写一个闭包例子 3. 改成生成器版本"

# 拆分预览（不执行）
st run "1. A 2. B 3. C" --dry-run -v

# 深度思考 + 专家模式
st ask "复杂问题" --deep-think --expert

# 上传文件分析
st ask "分析这个代码" -f ./src/main.py

# 多任务 + 文件（第一轮嵌入文件，后续轮次有上下文）
st run "1. 分析复杂度 2. 提出优化" -f ./quicksort.py

# JSON 输出
st run "..." -j

# 查看日志
st log tail -f
```

## 流水线架构

```
st run "1. A 2. B 3. C"
        │
   任务拆分（启发式）
        │
   同一 Chat 逐轮对话
   Turn 1: A → 等回答
   Turn 2: B → AI 记得 Turn 1 的上下文
   Turn 3: C → AI 记得 Turn 1+2
        │
   结果合并输出
```

## 支持的供应商

| 供应商 | 网址 | 状态 |
|--------|------|------|
| DeepSeek | chat.deepseek.com | ✅ 完整 |
| 元宝 | yuanbao.tencent.com | 🔧 基础 |
| Kimi | kimi.moonshot.cn | 📋 基础 |
| 豆包 | doubao.com | 📋 基础 |

## DeepSeek 特性

| 功能 | 标志 | 说明 |
|------|------|------|
| 深度思考 | `--deep-think` | 显示 AI 推理过程 |
| 专家模式 | `--expert` | 更详细的技术回答 |
| 联网搜索 | `--web-search` / `--no-web-search` | 默认开启 |
| 文件上传 | `-f file.py` | 嵌入文件内容到对话 |

## 前置要求

- **OpenCLI**: `npm install -g opencli`（需 Chrome + 扩展）
- **浏览器登录**: 目标 AI 网站需在 Chrome 中已登录
- **Python 3.10+**

## 项目结构

```
save_token/
├── cli.py              # Click CLI（st ask / st run / st log）
├── core.py             # 核心引擎（重试/日志）
├── orchestrator.py     # 🆕 完整流水线（拆分→对话→合并）
├── task_splitter.py    # 🆕 任务拆分（启发式+LLM）
├── async_engine.py     # 🆕 异步并行引擎
├── merger.py           # 🆕 结果合并
├── logging.py          # 🆕 结构化日志
├── opencli_bridge.py   # OpenCLI 命令封装
├── config/
│   └── manager.py      # TOML 配置管理
└── providers/
    ├── base.py         # Provider 基类
    ├── registry.py     # 自动发现
    ├── deepseek.py     # DeepSeek Chat（完整）
    └── yuanbao.py      # 腾讯元宝
```
