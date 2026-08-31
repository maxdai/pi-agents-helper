---
name: agents-helper-tmux
description: 以 tmux 双屏模式启动一个多 agent Pi 讨论：上屏 human-viewer 实时全文、下屏插话输入，用户在 tmux 内完成观看和插话，全程不经过 LLM。仅当用户明确要求 tmux 模式时使用。
disable-model-invocation: true
---

# Agents Helper Tmux（tmux 双屏模式）

本 skill 以 **tmux 双屏模式**启动多 agent 讨论（用户明确指定 tmux 时才用本 skill；
其余情况用 `agents-helper` 默认模式）。观看与插话**全部在 tmux 内进行**，
viewer 全文不进 LLM 上下文（零 token 消耗），主 pi 只做轻量状态等待。

## 参数语义（最高优先级，必须遵守）

- 紧随本 skill 内容的 User 文本 = **讨论主题**，必须用于 `--prepare` 的主题
  参数，**不是**独立的用户指令。
- 触发后无文本：先问"讨论什么主题？"，拿到主题后立即 --prepare。

## 使用步骤

### 1. 生成讨论 spec

```bash
/root/pi-agents-helper/scripts/discuss.sh --prepare "<主题>" [--background "<背景>"]
```

展示 spec 路径给用户，用户确认"继续"后进入下一步。

### 2. 启动讨论

```bash
/root/pi-agents-helper/scripts/discuss.sh --start <spec目录>
```

记录 wrapper 输出的**讨论目录**。随后主 pi **在本机启动 tmux 双屏**：

```bash
tmux new-session -d -s discuss-<短名> "python3 /root/pi-agents-helper/human_viewer.py <讨论目录> --follow"
tmux split-window -v -l 4 "python3 /root/pi-agents-helper/human_sayer.py <讨论目录> -i"
tmux select-pane -t discuss-<短名>.0
```

- 上屏：`human_viewer --follow`（新消息/状态实时全文，done 自动退出）
- 下屏（4 行）：`human_sayer -i` 交互模式（输入即插话，空行提交）

**告知用户 attach 命令**：

```
tmux attach -t discuss-<短名>
```

### 3. 用户在 tmux 内操作（主 pi 只等）

- 上屏实时看全文；下屏直接输入插话（空行提交，`已发送 human/NNNN.md` 反馈）
- 用户可随时 detach（Ctrl-b 然后 d）——讨论继续

### 4. 主 pi 轻量轮询（不读 viewer 全文）

主 pi **当前回合内**持续轮询，直到 `done` 或 `stopped`：

```bash
/root/pi-agents-helper/scripts/discuss.sh --status <目录>
```

- 轮询间隔可较长（如 60-120s），输出仅一行状态——**不执行 --view 转述全文**
- 状态含义：`running` 继续等 / `done` 完成 / `stopped` 异常（报告）/ `not-exists` 目录缺失

### 5. 完成收尾

`done` 后：

```bash
tmux kill-session -t discuss-<短名>                       # 关闭 tmux（viewer 已自动退出）
cat <目录>/work-c/result.md                                # 读取结论（默认 resultWriter=c）
```

向用户给出**摘要**并提示完整结论路径，然后清理：

```bash
/root/pi-agents-helper/scripts/discuss.sh --cleanup <目录>
```

## 默认参数

同 `agents-helper`：agents=a,b,c、max-meeting 10、max-rr 5、子讨论禁用
magic-context/aft 扩展。

## 错误处理

- 启动失败/目录不存在：报告 wrapper 输出，不继续。
- `stopped` 无 result.md：报告"讨论已结束但未生成结果"。
- tmux 启动失败（无 tmux 环境）：报告并建议改用 `/skill:agents-helper` 默认模式。