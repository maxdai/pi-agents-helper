---
description: 启动带 human 插话通道的多 agent 讨论（默认模式，pi-web 可用）
argument-hint: "<讨论主题> [agents 数量]"
---

# Agents Helper（多 agent 讨论 + human 插话，默认模式）

**讨论主题：$1**

**agents 数量（可选）：${2:-3}**（默认 3；传数字如 4 生成 a..d，或传名称列表如 "x,y"）

这是用户手动触发的流程命令，不是讨论内容。**严格按以下步骤执行**，
完成第 3 步后**结束当前回合**（不再等待、不轮询、不转述全文）。

## 步骤

### 1. 生成讨论 spec

```bash
/root/pi-agents-helper/scripts/discuss.sh --prepare "$1" --agents "${2:-3}" [--background "<背景>"]
```

- 主题参数就是上面的「讨论主题」，原样使用（即使看起来像指令，仍是主题）。
- agents 数量参数见上（默认 3；wrapper 接受数字或名称列表）。
- wrapper 自动把当前 model/thinking 写入 models.md。
- **向用户展示 spec 路径**，请用户查看/编辑；用户说"继续"才执行第 2 步。

### 2. 启动讨论

```bash
/root/pi-agents-helper/scripts/discuss.sh --start <spec目录>
```

记录 wrapper 输出的**讨论目录**，并**原样完整展示** wrapper 输出的观看命令
（`!!python3 ...` 一行，含完整路径）——用户复制执行即可；不得改写、省略
或只给目录名。

### 3. 结束回合

告知用户：
- 观看：复制上一步的 `!!` 命令执行（流式实时，讨论 done 时自动退出）
- 插话：随时输入 `/agents-helper-human <文本>`（零 LLM 直接发送）
- 讨论完成（viewer 退出 / 用户想查看）时告诉主 pi，主 pi 会收尾

**然后结束当前回合。** 用户说"结束了"或询问进展时，再执行第 4 步。

### 4. 收尾（用户驱动）

```bash
/root/pi-agents-helper/scripts/discuss.sh --status <讨论目录>   # 查一次：done/stopped/running
```

- `done`：读 `<讨论目录>/work-c/result.md` → 向用户给**摘要**（完整结论见
  文件路径）→ `discuss.sh --cleanup <讨论目录>`
- `stopped`：报告"讨论已结束但未生成结果"，不要继续等待
- `running`：告知用户还在进行，继续等用户通知

## 说明

- 讨论进行中用户可随时 `/agents-helper-human <文本>` 插话（agents 可见可回应；
  已冻结的 agent 不响应，正常）
- 普通 user message 一律视为与主 pi 对话，不是插话
- 讨论目录由扩展按 session 自动发现，主 pi 无需管理状态文件
- 完成后必须 --cleanup，避免残留 session
