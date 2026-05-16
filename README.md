# Save-Token

**用免费 AI 替代付费 API Token 的命令行工具。**

通过浏览器自动化（OpenCLI）操控 DeepSeek、元宝、Kimi 等免费 AI 聊天页面，无需 API Key。

## 快速开始

```bash
# 安装
pip install -e .

# 提问（默认 DeepSeek）
st ask "用 Python 写一个快排"

# 指定供应商
st ask "今天天气怎么样" -p yuanbao

# 查看思考过程
st ask "解释量子纠缠" -t

# JSON 输出（供程序调用）
st ask "1+1" -j

# 查看可用供应商
st providers

# 配置
st config show
st config set provider.default.name yuanbao
```

## 支持的供应商

| 供应商 | 网址 | 费用 | 状态 |
|--------|------|------|------|
| DeepSeek | chat.deepseek.com | 免费 | ✅ |
| 元宝 | yuanbao.tencent.com | 免费 | 🔧 |
| Kimi | kimi.moonshot.cn | 免费 | 📋 |
| 豆包 | doubao.com | 免费 | 📋 |

## 前置要求

- **OpenCLI**: `npm install -g opencli`（需 Chrome + 扩展）
- **浏览器登录**: 目标 AI 网站需在 Chrome 中已登录
- **Python 3.10+**

## 项目结构

```
save_token/
├── cli.py            # Click CLI 入口
├── core.py           # 核心引擎（重试/日志）
├── opencli_bridge.py # OpenCLI 命令封装
├── config/
│   └── manager.py    # TOML 配置管理
└── providers/
    ├── base.py       # Provider 基类
    ├── registry.py   # 自动发现
    ├── deepseek.py   # DeepSeek Chat
    └── yuanbao.py    # 腾讯元宝
```

## 自我进化

当 AI 网站更新 UI 时，只需修改对应 `providers/xxx.py` 中的选择器和 JS 提取逻辑。Provider 模块通过注册表自动发现，无需改动其他文件。

```bash
# 更新到最新版
git pull && pip install -e .

# 添加新供应商：复制 deepseek.py → 修改 PROVIDER_CONFIG 和 selectors
```
