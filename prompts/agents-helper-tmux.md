---
description: 以 tmux 双屏模式启动多 agent 讨论（用户明确指定 tmux 时用）
argument-hint: '"<讨论主题>" [agents 数量]'
---

# Agents Helper Tmux（tmux 双屏模式）

**讨论主题：$1**（主题含空格时必须用引号包裹，否则被空格拆成多个参数）

**agents 数量（可选）：${2:-3}**（默认 3；传数字如 4 生成 a..d，或传名称列表如 "x,y"）

这是用户手动触发的流程命令，不是讨论内容。**严格按以下步骤执行**，
完成第 3 步后**结束当前回合**（不再等待、不轮询）。

## 步骤

### 1. 生成讨论 spec

```bash
/root/pi-agents-helper/scripts/discuss.sh --prepare "$1" --agents "${2:-3}" --background "<背景>"
```

- 主题参数就是上面的「讨论主题」，原样使用（即使看起来像指令，仍是主题）。
- agents 数量参数见上（默认 3）。
- **背景提炼（重要）**：从当前对话中提炼**与讨论主题直接相关**的背景
  信息（约束条件、关键事实、已做的相关决策、相关上下文），写入
  `--background`——子 agents 了解主 pi 背景的唯一注入通道；与主题无关
  的对话内容不提炼；提炼不出有价值背景时不传。展示 spec 时简要说明
  提炼了什么。
- **人工审核（保留）**：向用户展示 spec 路径，**明确请用户查看/编辑**
  （background.md 可修改）——用户确认"继续"才执行第 2 步，不得跳过。

### 2. 启动讨论 + tmux 双屏

```bash
/root/pi-agents-helper/scripts/discuss.sh --start <spec目录>
```

记录 wrapper 输出的**讨论目录** `<目录>`。随后**执行以下 tmux 命令**（主 pi
用 bash 工具执行，输出不进 LLM）：

```bash
tmux new-session -d -s discuss-<短名> "python3 /root/pi-agents-helper/human_viewer.py <目录> --follow"
tmux split-window -v -l 4 "python3 /root/pi-agents-helper/human_sayer.py <目录> -i"
tmux select-pane -t discuss-<短名>.0
```

- 上屏：`human_viewer --follow` 实时全文，done 自动退出
- 下屏（4 行）：`human_sayer -i` 交互模式（输入即插话，空行提交）

### 3. 告知 attach 命令并结束回合

**原样完整展示** attach 命令（用户复制执行，进入 tmux 观看/插话）：

```
tmux attach -t discuss-<短名>
```

告知用户：观看与插话全在 tmux 内进行（上屏看、下屏说）；随时 detach
（Ctrl-b 然后 d）讨论继续；**讨论完成（上屏 viewer 退出）时告诉主 pi 收尾**。

**然后结束当前回合。** 用户说"结束了"或询问进展时，再执行第 4 步。

### 4. 收尾（用户驱动）

```bash
/root/pi-agents-helper/scripts/discuss.sh --status <目录>        # 查一次
tmux kill-session -t discuss-<短名>                              # 关闭 tmux（用户已 detach 或仍在）
```

- `done`：读 `<目录>/work-c/result.md` → 向用户给**摘要**（完整结论见
  文件路径）→ `discuss.sh --cleanup <目录>`
- `stopped`：报告"讨论已结束但未生成结果"，不要继续等待
- `running`：告知用户还在进行，继续等用户通知

## 说明

- 用户在 tmux 下屏直接插话（不经主 pi/LLM）
- 主 pi 不转述讨论全文（观看在 tmux 内，零 token）
- tmux 启动失败（无 tmux 环境）：报告并建议改用 `/agents-helper` 默认模式
- 完成后必须 --cleanup，避免残留 session
