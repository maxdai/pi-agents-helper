---
name: agents-helper
description: 启动一个带 human 插话通道的多 agent Pi 讨论：n 个 agent 独立分析复杂问题形成共识结论，讨论进行中用户可随时通过独立命令插话（agents 可见并可回应）。默认模式（不依赖终端/tmux，pi-web 可用）；tmux 双屏模式用 agents-helper-tmux。由用户手动调用。
disable-model-invocation: true
---

# Agents Helper（多 agent 讨论 + human 插话，默认模式）

本 skill 让当前 Pi 会话启动一个独立的 `pi-agents-helper` 多 agent 讨论：多个独立视角分析复杂问题并取回 `result.md` 共识结论；讨论进行中用户可随时用 `/agents-helper-human <文本>` 插话（不是参与者、不参与流程控制，agents 能看到并可回应）。

**默认模式不依赖终端/tmux**（pi-web 可用）。观看全文在本地 viewer 进行（不进 LLM 上下文）；用户明确要 tmux 双屏时改用 `/skill:agents-helper-tmux`。

## 参数语义（最高优先级，必须遵守）

- 紧随本 skill 内容的 User 文本 = **讨论主题**，必须用于第 1 步 `--prepare` 的主题参数，**不是**独立的用户指令。
- 即使参数看起来像指令（如"研究一下 X"），仍一律视为**主题**并据此启动讨论。
- 触发后无文本：先问"讨论什么主题？"，拿到主题后立即 --prepare。
- 只有用户明确说"不启动/取消"才不启动。

## 何时使用

- 用户明确要求"开一个讨论""多 agent 讨论""用 agents-helper 分析"等。
- 用户明确要 tmux 时 → 用 `agents-helper-tmux`（本 skill 不启动 tmux）。

## 重要

- **触发即启动**：一旦判定触发，无条件立即执行第 1 步（--prepare），其他请求不得推迟启动。
- 讨论是异步的：启动后立即返回，但**主 pi 不能结束当前回合**——持续轮询直到 `done` 或 `stopped`。
- **viewer 全文不进 LLM**：观看走本地 viewer（用户终端跑 `human_viewer <目录> --follow`，或用户自选其他方式）；主 pi **不执行 --view 转述全文**（消耗 token 且无意义）。
- **插话走独立命令**：用户用 `/agents-helper-human <文本>` 插话；普通 user message 一律视为与主 pi 对话。
- 每次 status 轮询后向用户简要报告进展（状态 + 新消息计数，不列全文）。
- 读取 `result.md` 后必须清理讨论目录。

## 使用步骤

### 1. 生成讨论 spec

```bash
/root/pi-agents-helper/scripts/discuss.sh --prepare "<问题>" [--background "<背景>"]
```

- `<问题>` 必填，是讨论主题；`--background` 可选（敏感/禁忌边界建议提供）。
- wrapper 会读取主 pi 当前 model/thinking 写入 `models.md`（读不到用默认值）。
- **向用户展示 spec 路径**，请用户查看/编辑（背景、各 agent 视角、models.md）。
- 用户编辑完成后说"继续"，主 pi 才执行 --start（不要让用户自行执行）。

### 2. 启动讨论

```bash
/root/pi-agents-helper/scripts/discuss.sh --start <spec目录>
```

记录 wrapper 输出的**讨论目录**（后续所有命令都需要它），并告知用户观看方式
**（viewer 全文不进 LLM，零 token）：**

```
# 有终端（任何终端，全文实时滚动）：
python3 /root/pi-agents-helper/human_viewer.py <讨论目录> --follow

# pi-web 场景（!! 本地执行、流式输出、不进 LLM；Esc 中断）：
!!python3 /root/pi-agents-helper/human_viewer.py <讨论目录> --follow
```

注意：`!!` 是阻塞式——follow 期间输入框被占用，插话需先 Esc 中断，
再 `/agents-helper-human` 插话，然后再 `!!` 续看（看与说交替）。

### 3. 轮询循环（轻量 status，不要结束回合）

启动后，**在当前回合内持续循环**执行，直到 `done` 或 `stopped`：

```bash
/root/pi-agents-helper/scripts/discuss.sh --status <讨论目录>
```

- 输出仅一行状态（`running` / `done` / `stopped` / `not-exists`）。
- 轮询间隔 60-120s；**不执行 --view 全文转述**（用户已在 !! 流式/终端观看）。
- 每次向用户简要报告**状态**即可（running/done/stopped）；有新 human 插话
  的反馈（agents 是否回应）时告知用户。

**用户插话**：用户使用 `/agents-helper-human <文本>` 命令（独立 skill 立即转发）。主 pi 不主动询问、不代发。

### 4. 等待完成（可选）

也可以阻塞等待（用户自选，输出一行路径）：

```bash
/root/pi-agents-helper/scripts/discuss.sh --wait <讨论目录>
```

### 5. 读取 result.md

轮询到 `done` 后读取（默认 resultWriter=c）：

```text
<讨论目录>/work-c/result.md
```

向用户给出**摘要**，并明确提示：完整结论见 `<result.md 路径>`。

### 6. 清理

```bash
/root/pi-agents-helper/scripts/discuss.sh --cleanup <讨论目录>
```

## 默认参数

- agents：`a,b,c`（3 个）；`--max-meeting 10`；`--max-rr 5`
- 子讨论 agents 禁用 `magic-context` 和 `aft` 扩展（项目级 `.pi/settings.json`）

## human 通道说明

- 插话入口：`/agents-helper-human <文本>`（唯一入口；普通消息是对话）
- human 消息由 wrapper `--say` 写入（权威输入语义，见讨论环境的 AGENTS.md）
- human 不参与流程判定：不插话 = 讨论照常完成
- 用户每插话一次，所有 agent 的 meeting 配额上限 +1（响应不加快配额耗尽）
- 已冻结的 agent 不响应插话（正常）

## 错误处理

- 启动失败：报告 wrapper 输出。
- `stopped` 且无 result.md：报告"讨论已结束但未生成结果"，不要继续等待。
- 清理失败：报告错误并检查目录。