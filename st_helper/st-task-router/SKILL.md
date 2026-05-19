---
name: st-task-router
description: "判断任务是否应该使用 st 命令执行。原子性任务用 st（省Token），复杂任务用 Hermes。每次接到新任务时自动加载此 skill。"
triggers:
  - "写一个"
  - "写代码"
  - "分析"
  - "解释"
  - "查一下"
  - "生成"
  - "修复"
  - "帮我"
---

# ST Task Router

判断用户请求是否可以用 `st` 命令完成。原子性任务用 `st`（零Token），复杂多步任务保持用 Hermes。

## 判断规则

### ✅ 用 `st` 的原子任务（独立、可一次完成）

| 类型 | 示例 | 用哪个 |
|------|------|--------|
| 代码生成（单函数/脚本） | "写一个快排" | `st ask --local` |
| 代码生成（需高质量） | "写一个微服务框架" | `st ask -p deepseek --expert` |
| 概念解释 | "什么是闭包" | `st ask --local` |
| 实时信息 | "今天天气" | `st ask -p yuanbao` |
| 文件分析 | "分析这个代码" | `st ask -f file.py` |
| Bug 解释 | "为什么报这个错" | `st ask -p deepseek` |
| 翻译 | "翻译成英文" | `st ask --local` |
| 正则/算法 | "写个匹配邮箱的正则" | `st ask --local` |

### ❌ 用 Hermes 的复杂任务（需要多步/工具）

| 类型 | 示例 | 为什么 |
|------|------|--------|
| 需要读写文件 | "改一下 config.yaml" | 需要 file 工具 |
| 需要运行命令 | "跑一下测试" | 需要 terminal |
| 需要查项目上下文 | "修复 VirtualQuest 的 bug" | 需要读多个文件 |
| 多步操作 | "创建项目、写代码、跑测试" | 需要编排 |
| Git 操作 | "提交代码" | 需要 git 工具 |
| 安装/部署 | "安装依赖" | 需要 terminal |

## 使用流程

```
收到用户请求
    │
    判断：是否原子任务？
    ├── 是 → 选 provider → 执行 st ask/run → 返回结果
    └── 否 → Hermes 自己处理
```

## Provider 速选

- 简单代码/概念 → `st ask "..." --local`（2s，零成本）
- 需要实时数据 → `st ask "..." -p yuanbao`（8s）
- 需要高质量代码 → `st ask "..." -p deepseek --expert`（38s）
- 快速回答 → `st ask "..." -p doubao`（6s）
- 多步递进 → `st run "1. 2. 3."`（同一Chat）

## 示例

```
用户: "写一个Python单例模式"
判断: ✅ 原子任务 → st ask --local

用户: "修复 save-token 的文件上传 bug"
判断: ❌ 复杂任务 → Hermes 处理（需要读代码、改文件、测试）

用户: "今天深圳天气怎么样"
判断: ✅ 原子任务 → st ask -p yuanbao

用户: "把VirtualQuest的前端改成暗色主题"
判断: ❌ 复杂任务 → Hermes 处理（需要读Vue文件、改CSS、验证）
```
