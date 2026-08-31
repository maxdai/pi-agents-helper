---
name: agents-helper-human
description: 向正在进行的多 agent 讨论插话：把用户文本作为 human 消息注入讨论，agents 可见并可回应。由用户手动触发（讨论进行中随时可用）。
disable-model-invocation: true
---

# Agents Helper Human（讨论插话）

本 skill 把用户的文本作为 **human 插话**注入当前正在进行的多 agent 讨论——agents
能看到并可回应。**仅用于插话**；用户的其他输入一律是普通对话（与主 pi 交流），
不要视为插话。

## 参数语义（最高优先级，必须遵守）

- 紧随本 skill 内容的 User 文本 = **插话内容**，必须原样作为 `--say` 的文本
  参数发送给 agents——**不是**独立的用户指令，不得当作任务执行或回答。
- 触发后无文本：先问"要插话什么？"，拿到内容立即发送。

## 使用步骤

1. **确定当前讨论目录**：本会话中最近一次启动的讨论目录（`discuss.sh --start`
   输出的"目录:"路径）。若当前没有正在进行的讨论（已清理/未启动）→ 告知用户
   "没有正在进行的讨论"，不执行。
2. 执行插话：

```bash
/root/pi-agents-helper/scripts/discuss.sh --say <讨论目录> "<插话文本>"
```

3. 向用户反馈：`已发送 human/NNNN.md`，并简短说明 agents 下轮即可看到并可回应
   （已冻结的 agent 不响应，正常）。

## 注意

- 本 skill 一次触发 = 一次插话，**立即完成并返回**，不进入任何轮询/状态循环。
- 插话内容会原样写入讨论，保持文本完整（多行也完整保留）。
- 若用户想启动新讨论，用 `agents-helper` skill（本 skill 不启动讨论）。