# pi-agents-helper 设计文档

> 状态：设计讨论中（2026-08-30）
> 定位：`pi-agents-meeting-discuss` 的衍生项目——保持原有多 agent 讨论协议
> 完全不变，**额外附加一个"人的插话"通道**：人不在参与者之列、不参与
> 流程控制，只是可以向讨论中注入信息，agents 能看到并（可选地）回应。

## 1. 演化链与项目定位

```
agents-rr-discuss（opencode，RR 轮转模式）
  → agents-meeting-discuss（opencode，meeting 自由讨论 + 冻结级联 + RR 收尾）
  → pi-agents-meeting-discuss（pi 运行时 + skill 包装）
  → pi-agents-helper（本项目：+ human 插话通道）
```

`pi-agents-helper` 复用 pi-agents-meeting-discuss 的全部协议、状态机、环境生成、
测试装置，**只增加 human 插话能力**。n 个 LLM agents 的讨论逻辑流程完全不变。

## 2. 核心设计：信息层与流程层分离

human 插话是**纯信息注入**。一条 human 消息 = 往共享信息池（bare 仓库）投一条
只读内容；它影响"agents 能读到什么"，**不参与任何流程判定**。

| 层 | 内容 | human 消息是否参与 |
|---|---|---|
| 信息层 | agents 的读取（`new_messages_with_meta` diff 范围） | ✅ 可见，可触发响应 |
| 流程层 | 状态判定（冻结/af/RR/收尾）、轮转链、配额、发言锁 | ❌ 视而不见（显式跳过） |

"视而不见"的准确语义：状态判定逻辑在遍历时**显式过滤**非参与者消息——
不是物理隔离，是判定时忽略。human 消息存在且可读，但状态机不看它。

### 2.1 人的身份

- human 是**附加的特殊 agent**，不属于设定的 n 个参与者
- 固定名 `human`（保留字）：`--agents` 传 `human` 报错（防止被当成普通参与者
  生成 loop 进程）
- 消息文件 `human/NNNN.md`（`^[a-z]+/\d{4}\.md$` 天然合法）
- 参与者的 loop 进程照常只启动 n 个；human 无 loop 进程，插话由外部工具触发

### 2.2 消息语义

human 消息 frontmatter 由工具确定性补全（人只提供正文）：

```
from: human
type: message          # 强制——人不写流程信号（freezing/pass/af/concluded）
mode: <写入时当前聚合 mode>   # 语义正确性（不参与判定，填当前阶段）
seen_at: <写入时 HEAD>       # 人看到了当前全部状态
to: all
summary: <一句话摘要>        # 可选，人可提供
```

- 人的消息不携带 `next`（不参与轮转链）
- 消息写入走与 agents 相同的 commit+push 路径（含并发容错重试）
- 人的消息同样计入"讨论已开始"与 stall 重置（HEAD 变化即进展）

## 3. 各阶段行为（语义推演）

### 3.1 meeting 阶段

- human 插话 → agents 的 `has_new_messages_for_me` 看到 `human/NNNN.md`
  （from=human, to=all）→ **配额内且未冻结**的 agent 被触发响应（内容回应）
- **已冻结 agent（发言锁）不响应** → 冻结状态不被解除
- 冻结级联、`should_write_af`、收敛判定只看 n 个参与者 → human 插话
  不推动也不阻塞流程
- 配额尽但未冻结的 agent：human 插话带来的配额增量使其获得回应机会
  （见 §4）

### 3.2 all-freezing 阶段

- starter 检测到 human 新消息 → 唤醒 LLM 读取 human 内容后再确定性写 pass
  （现有"冻结期间新消息"逻辑天然覆盖，LLM 只多读一条内容）
- 轮转顺序不变

### 3.3 round-robin 阶段

- **human 不参与轮转**：轮转链完全由 n 个参与者的 `next` 链驱动
- `rr_next_speaker` 读 bare HEAD 消息时**跳过非参与者消息**，往前找最后一条
  参与者消息的 next（否则 human 插话后 HEAD=human 消息 → next 缺失 → 断链）
- 轮到的 agent 唤醒时多读到 human 内容，照常写 pass（单向流）
- 全员 pass 判定只看参与者 → human 插话不影响收尾触发

### 3.4 收尾

- resultWriter 收尾逻辑不变；human 消息不影响 `concluded` 判定

## 4. 配额：human 发言给所有 agent 配额 +1

human 引发的 agent 响应**计入**该 agent 的 meeting 发言配额（
`_meeting_speak_count` 不变——数 mode=meeting 且 type=message 的消息）。
为抵消响应消耗，**human 每发一条消息，所有 agent 的配额上限 +1**：

```
配额耗尽判定：speak_count >= max_meeting + human_msg_count
（human_msg_count = bare 中 human/ 目录的消息数，从共享事实推导）
```

净效果：

| agent 行为 | 消耗 | 配额上限增量 | 净效果 |
|---|---|---|---|
| 响应了 human | +1 | +1 | 净 0（不加快耗尽）✅ |
| 未响应 human | 0 | +1 | 可用轮 +1（讨论空间略增） |

优点：
- 实现一行改动（判定上限 + h_count），`_meeting_speak_count` 无需区分
  "响应 human 的消息"（`in_reply_to` 不可靠，不需要）
- 从共享事实推导，无状态传递、崩溃安全
- 对全体 agent 对称（既不清零、也不单独奖励响应者）

边界：
- human 插话后，配额尽**但未冻结**的 agent 获得回应机会（⑤.2 条件不再满足
  → 响应 human）——设计意图
- **已冻结 agent 不解冻**（发言锁优先）——与"human 不解除冻结"语义一致

## 5. 实现清单（阶段 1：核心脚本）

| # | 改动 | 位置 |
|---|---|---|
| 1 | human writer 工具：pull → 取 head/mode → 写 `human/NNNN.md`（frontmatter 补全，type 强制 message）→ commit+push | 新命令（start_discussion.py 子命令 或 独立脚本） |
| 2 | `rr_next_speaker` 跳过非参与者消息（往前找最后一条参与者消息的 next） | meeting_engine.py |
| 3 | 配额判定：`max_meeting + human_msg_count` | meeting_engine.py |
| 4 | setup：额外建 `work-human/` clone（不启动 loop）+ `human` 保留名校验 | start_discussion.py |
| 5 | 测试：meeting/RR 阶段插话、轮转链不断、配额不加快耗尽、冻结不解冻 | tests/ |

### 5.1 关键实现细节

- **human_msg_count 从哪读**：循环顶 ls-tree 已列全部文件（
  `_each_agent_messages` 同源），派生 `human/` 目录消息数；判定只看参与者
  的不变量保持（h_count 是配额增量输入，不是状态判定）
- **保留名校验**：`--agents`/spec/agents 中出现 `human` → 明确报错
  （"human 是保留名，不参与讨论，请使用插话通道"）
- **work-human 的用途**：仅作 human writer 的提交通道（clone + git 身份），
  不启动任何 loop 进程

## 6. 阶段划分

- **阶段 1（当前）**：核心脚本功能 + 测试调试（本文档 §5）
- **阶段 2（调试通过后）**：skill 层——SKILL.md、discuss.sh wrapper、npm 包装、
  主 pi 插话入口流程（用户通过主 pi 会话插话）

## 7. 测试策略

| 层 | 内容 |
|---|---|
| 单元 | 配额增量判定、rr_next_speaker 跳过、human writer frontmatter 生成 |
| FakeAgent 多进程 | 带 human 插话的 meeting/RR 完整讨论：轮转不断、收敛正常 |
| 边界 | 冻结中插话不解冻、RR 中插话不断链、配额尽未冻结者获得回应机会 |
