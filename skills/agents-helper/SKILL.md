---
name: agents-helper
description: 启动一个带 human 插话通道的多 agent Pi 讨论：n 个 agent 独立分析复杂问题形成共识结论，期间人可以随时插话（提供信息/纠正方向，agents 可见并可回应）。由用户手动调用。
disable-model-invocation: true
---

# Agents Helper（多 agent 讨论 + human 插话）

本 skill 让当前 Pi 会话启动一个独立的 `pi-agents-helper` 多 agent 讨论：多个独立视角分析复杂问题并取回 `result.md` 共识结论；讨论进行中**人可以随时插话**——不是参与者、不参与流程控制，只是注入信息（agents 能看到并可回应）。

## 何时使用

- 用户明确要求"开一个讨论""多 agent 讨论""用 agents-helper 分析"等。
- 当前问题复杂、需要多角度论证时，由用户决定是否调用。

## 重要

- 本 skill 由用户手动触发，不要自行判断触发。
- 讨论是异步的：启动后立即返回，但**主 pi 不能结束当前回合**。
- 启动后必须持续轮询状态，直到 `done` 或 `stopped`，再结束回合。
- 每次轮询后必须向用户报告进展。
- **human 插话是主通道**：每轮用 `--view` 增量展示新消息后，询问用户是否插话；用户给出内容后立即 `--say`。
- 读取 `result.md` 后必须清理讨论目录，避免残留 session。

## 使用步骤

### 1. 生成讨论 spec

运行：

```bash
../../scripts/discuss.sh --prepare "<问题>" [--background "<背景>"]
```

- `<问题>` 必填，是讨论主题。
- `--background` 可选；如果话题涉及敏感/禁忌边界，建议提供背景说明。

wrapper 会自动基于当前工作目录定位主 pi 的 session 文件，读取当前 model/thinking，并写入 `models.md`；如果读取不到，则使用默认值。

wrapper 会生成一个临时 spec 目录，并输出路径。

**向用户展示 spec 路径，请用户查看/编辑该目录**（可以补充背景、各 agent 视角、或修改 `models.md` 中的 model/thinking）。

**不要**让用户自行执行 `--start`。用户编辑完成后，告诉主 pi"继续"。

### 2. 启动讨论

用户确认"继续"后，主 pi 运行：

```bash
../../scripts/discuss.sh --start <spec目录>
```

启动后 wrapper 会输出讨论目录路径和 human 通道命令。**记录讨论目录**（后续命令都需要它）。

### 3. 轮询循环（human 插话 + 状态，不要结束回合）

启动后，**在当前回合内持续循环**执行以下三件事，直到 `done` 或 `stopped`：

**(a) 增量查看进展**：

```bash
../../scripts/discuss.sh --view <目录> --since <游标>
```

- 第一次轮询：不带 `--since`（看全部）。
- 之后：`--since` 用上一轮输出的 `HEAD=<hash>`（**记录输出末尾的 HEAD，作为下轮游标**——无状态，不写文件）。
- 输出 = 新消息（`[作者/序号] from (type): summary` + 正文）+ 状态变化 + 末尾 `HEAD=<hash>`。
- **向用户展示新消息**（有 human 消息时明确标注来源是 human）。

**(b) 询问用户是否插话**：

每轮都问（简短即可）："要插话吗？"用户给内容则：

```bash
../../scripts/discuss.sh --say <目录> "<文本>"
```

- 插话后告知用户已发送；agents 下轮即看到并可回应（**已冻结的 agent 不会响应**，正常）。
- 用户每插话一次，所有 agent 的 meeting 配额上限 +1（响应不加快配额耗尽）。

**(c) 查看状态**：

```bash
../../scripts/discuss.sh --status <目录>
```

可能的状态：

- `running`：讨论仍在进行，继续轮询。
- `done`：讨论完成，`result.md` 已生成。
- `stopped`：讨论进程已结束，但没有 `result.md`——报告错误。
- `not-exists`：目录不存在，检查路径。

**每次轮询后必须向用户报告进展**：新消息摘要 / 是否插话 / 当前状态。只有出现 `done` 或 `stopped` 才停止轮询。

### 4. 等待完成（可选）

也可以阻塞等待：

```bash
../../scripts/discuss.sh --wait <目录>
```

完成时会打印 `result.md` 路径。

### 5. 读取 result.md

- 如果使用 `--wait`，按它打印的路径读取。
- 如果使用 `--status` 轮询到 `done`，默认读取：

```text
<目录>/work-c/result.md
```

读取后，向用户给出**摘要**，并明确提示：

> 完整结论见 `<result.md 路径>`。

### 6. 清理

读取完 `result.md` 后，必须清理讨论目录：

```bash
../../scripts/discuss.sh --cleanup <目录>
```

## 默认参数

启动讨论时 wrapper 使用以下默认值：

- agents：`a,b,c`（3 个）
- `--max-meeting 10`
- `--max-rr 5`
- 子讨论 agents 默认**禁用 `magic-context` 和 `aft`** 两个扩展（通过项目级 `.pi/settings.json`），其它扩展正常加载

## human 通道说明（与纯 meeting-discuss 的区别）

- 讨论中用户可以随时插话（提供新事实、纠正、方向提示）——agents 看到后**必须认真对待**（权威输入语义，见 work 的 AGENTS.md）
- human 消息由主 pi 代发（`--say`），**不要**让用户直接执行任何命令
- human 不参与流程判定：不插话 = 讨论照常完成；插入的消息不阻塞/不推动流程
- 有终端时用户也可另开 tmux 双屏观看（`discuss.sh --view --follow` 形态），与本流程互不干扰

## 错误处理

- 启动失败：wrapper 会输出具体错误，向用户报告即可。
- `stopped` 且没有 `result.md`：报告"讨论已结束但未生成结果"，不要继续等待。
- 清理失败：报告错误并检查目录。