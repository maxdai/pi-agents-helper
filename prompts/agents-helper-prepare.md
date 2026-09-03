---
description: 提炼当前上下文中与讨论主题相关的背景，写入 discuss_prepare 文件（供 agents-helper 启动讨论时使用）
argument-hint: '"<讨论主题>"'
---

# Agents Helper Prepare（讨论背景提炼）

**讨论主题：$1**

这是用户手动触发的流程命令，不是讨论内容。你**唯一的职责**：提炼背景 →
写入 discuss_prepare 文件 → 告知路径 → 结束回合。**不启动讨论、不做其它事。**

## 步骤

### 1. 提炼背景

从当前对话上下文与项目记忆中提炼**与讨论主题直接相关**的背景信息：

- 只提炼影响理解主题或决策的信息（约束条件、关键事实、已做的相关决策、
  相关上下文）；与主题无关的内容一律不提炼
- 提炼不出有价值背景时，背景节写「（无）」，不硬凑

提炼遵循规范：
~/.pi/agent/npm/node_modules/pi-agents-helper/docs/background-distillation.md
（提炼时先读对照；已熟悉可跳过）

### 2. 写入 discuss_prepare 文件

文件名必须带 session id（bash 环境 `PI_SESSION_ID` 变量）：

1. 先执行 `echo "discuss_prepare_${PI_SESSION_ID}.md"` 得到确切文件名
2. 用 write 工具把以下内容写入该文件（**严格保持此格式**，在当前目录）：

```markdown
# 讨论主题
<主题原文>

# 背景
<提炼的背景正文>
```

注意：不要改动两节的标题文字；背景正文保持多行原样。
**文件可能已存在（上次 prepare 的产物）——直接覆盖写入，不要先读旧文件、
不要询问确认**：最新提炼生效是预期行为（cleanup 时该文件会被删除）。

### 3. 结束回合

告知用户：
- 文件路径（完整）
- 下一步：触发 `/agents-helper` 启动讨论（启动后审核 spec 时，可把本文件
  「# 背景」节内容复制进 spec 的 background.md）

**然后立即结束当前回合。**
