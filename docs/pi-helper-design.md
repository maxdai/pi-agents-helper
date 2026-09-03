# pi-agents-helper 设计文档

> 状态：设计讨论中（2026-08-30）
> 定位：`pi-agents-meeting-discuss` 的衍生项目——保持原有多 agent 讨论协议
> 完全不变，**额外附加一个"人的插话"通道**：人不是参与者、不参与流程控制，
> 只是可以向讨论中注入信息，agents 能看到并（可选地）回应。

## 1. 项目定位与演化链

### 1.1 演化链

```
agents-rr-discuss（opencode，RR 轮转模式，最初版本）
  → agents-meeting-discuss（opencode，meeting 自由讨论 + 冻结级联 + RR 收尾）
  → pi-agents-meeting-discuss（pi 运行时 + skill 包装）
  → pi-agents-helper（本项目：+ human 插话通道）
```

每一代继承上一代的核心不变式：**确定性归 loop、状态从 git 共享事实推导、
单一事实源 = protocol.json、无静默铁律、一次讨论 = 一个自包含目录**。

### 1.2 本项目的增量

pi-agents-helper 复用 pi-agents-meeting-discuss 的**全部**协议、状态机、环境
生成、测试装置，只增加 human 插话能力。n 个 LLM agents 的讨论逻辑流程
完全不变——这是硬约束：任何改动不得改变 participants 之间的状态判定、
轮转、收敛、收尾行为。

### 1.3 动机

原系统讨论完全发生在 LLM agents 之间，人是旁观者（只能等 result.md）。
实际使用中用户可能希望：
- 讨论中途提出新问题/新信息（agents 没考虑到的角度）
- 纠正 agents 对事实的理解偏差
- 给讨论注入方向性提示（但不强制）

**人的插话 = 信息注入，不是流程干预**（本版本）。强制收尾/暂停等流程干预
不在本版本范围（见 §10 开放问题）。

## 2. 核心设计：信息层与流程层分离

human 插话是**纯信息注入**。一条 human 消息 = 往共享信息池（bare 仓库）
投一条只读内容；它影响"agents 能读到什么"，**不参与任何流程判定**。

| 层 | 内容 | human 消息是否参与 |
|---|---|---|
| 信息层 | agents 的读取（`new_messages_with_meta` 的 diff 范围） | ✅ 可见，可触发响应 |
| 流程层 | 状态判定（冻结/af/RR/收尾）、轮转链、配额、发言锁 | ❌ 视而不见（显式跳过） |

**"视而不见"的准确语义**：状态判定逻辑在遍历时**显式过滤**非参与者消息——
不是物理隔离（human 消息存在于 bare、可被读取），是判定时忽略。参与者的
loop 进程读得到 human 消息（信息层），但状态机推导不看它（流程层）。

### 2.1 人的身份

- human 是**附加的特殊 agent**，不属于设定的 n 个参与者
- 固定名 `human`（保留字）：`--agents`/`spec/agents/` 中出现 `human` →
  明确报错（"human 是保留名，不参与讨论，请使用插话通道"）
- 消息文件 `human/NNNN.md`（`^[a-z]+/\d{4}\.md$` 正则天然合法，`is_message_file`
  零改动）
- 只启动 n 个参与者 loop 进程；human **无 loop 进程**，插话由 human-sayer
  单次触发；展示由 human-viewer 提供

### 2.2 消息语义（frontmatter）

human 消息 frontmatter 由 human-sayer 确定性补全，人只提供正文：

```
from: human
type: message          # 强制——人不写流程信号（freezing/pass/af/concluded）
mode: <写入时当前聚合 mode>   # 语义正确性；不参与判定（聚合只看参与者）
seen_at: <写入时 HEAD>       # 语义 = 人看到了当前全部状态（与 LLM 消息一致）
to: all
summary: <一句话摘要>        # 可选，自动截取正文首行
```

**各字段论证**：
- `type` 强制 `message`：新概念禁令——人不参与流程，不需要新类型；
  human 的任何输入（提问/纠错/提示）都是内容层消息
- `seen_at` 填写入时 HEAD：与 LLM 消息语义一致（"我看到/处理到此刻"）；
  使后续 `new_messages_with_meta` 的 stale 判定（该消息 seen_at 之后有更新
  → 陈旧）对 human 消息正常工作
- `mode` 填当前聚合 mode：human 消息不参与判定，填什么不影响流程；
  填当前阶段仅为信息完整性
- **不携带 `next`**：不参与轮转链（§3.4）

### 2.3 "视而不见"的代码落点（逐一核对）

| 判定 | 输入 | human 消息影响 |
|---|---|---|
| `_each_agent_messages(bare, agents)` | 遍历 agents（participants）目录 | ❌ 不含 human 目录 |
| `aggregate_mode`（mode 判定） | 每参与者最后一条 | ❌ |
| `should_write_af` / `can_start_rr` | 每参与者最后 type | ❌ |
| `rr_next_speaker` | bare HEAD 消息的 next | ⚠️ 需修复（§3.4） |
| `_meeting_speak_count` | 参与者消息数（mode=meeting, type=message） | ⚠️ 计数不含 human；配额上限 +h_count（§4） |
| `rr_active_count` | starter 的 RR 消息数 | ❌ |
| 触发判定 `has_new_messages_for_me` | diff 范围的新消息 | ✅ **唯一参与点**（from=human → 触发响应） |
| stall 判定（HEAD 变化） | bare HEAD | ✅ human 插话 = HEAD 变化 = 重置 stall（用户 2026-08-30 确认：自然语义，不改判定） |
| `_stall_elapsed` 的"讨论已开始" | bare 是否存在消息文件 | ✅ human 消息也算讨论开始（讨论确实开始了） |
| `--status` 的 done 判定 | result.md + concluded | ❌ |

**结论**：human 消息在流程层只经过两个"缝隙"——触发判定（设计意图，§3.1）
和 stall 重置（用户已确认，自然语义）；其余全部显式隔离。

## 3. 状态机逐分支推演

背景：`agent_loop` 每轮 = `git_pull → 读 bare 全量消息 → core 聚合判定 → 分派`。
以下逐分支分析 human 插话的行为。**前提**：human 插话 = human-sayer 完成
一次 commit+push（`human/NNNN.md` 进入 bare，HEAD 前移）。

### 3.1 meeting 阶段

**触发链**：human 插话 → 各 agent 的 `new_messages_with_meta` 的 diff
（`seen_at..HEAD`）包含 `human/NNNN.md` → `has_new_messages_for_me`（
from=human ≠ agent，to=all）→ **True** → 唤醒 LLM，human 消息进入 prompt。

**响应条件**（与普通消息完全一致的分支顺序）：

| agent 状态 | 行为 |
|---|---|
| 配额内 且 未冻结 | 唤醒响应（message/freezing） |
| 配额耗尽（未冻结） | ⑤.2 分支：因 h_count 配额增量可能不再耗尽（§4.3）→ 响应；否则确定性 freezing |
| 已冻结（发言锁） | **不响应**（⑤.4 锁优先）→ 冻结状态不被解除 |
| 唯一未冻结者（无新消息时） | human 消息存在 → triggered=True → 先响应 human，不自动冻结 |

**关键语义**：
- human 插话**不解除冻结**（发言锁优先，与"human 不干预流程"一致）
- 冻结级联判定只看参与者最后一条——human 插话不推动也不阻塞级联
- agent 对 human 的响应 = **普通发言**（与 agent 主动发言无区别）：它改变
  该 agent 自己的 last type、计入配额、可能触发其他 agent（链式，§4.4）——
  这是"agents 响应"的自然语义，不是 human 消息参与流程

**边界推演**：

| 场景 | 行为 | 正确性 |
|---|---|---|
| 全员已冻结（未写 af）时 human 插话 | 各 agent 触发判定 True → 发言锁挡住 → 不响应；级联继续 → af 照常 | ✅ 冻结不被破坏 |
| a/b 冻结、c 配额内未冻结时 human 插话 | 仅 c 响应；a/b 锁着 | ✅ |
| human 连续插话 2 条 | 触发 2 次；agents 响应节奏由自身 poll 决定；配额上限 +2 | ✅ 无新机制 |
| human 插话恰在 agent 写消息的同一瞬间 | push 并发 → 现有容错（pull --rebase → 重推）| ✅ 已有机制覆盖 |

### 3.2 冻结级联（freezing → all-freezing）

- 判定输入 = 参与者最后一条 ∈ {freezing, af} → 与 human 消息无关
- human 在级联过程中插话：已冻结者不响应、未冻结者响应后仍可能冻结
  （配额尽/无话）→ 级联最终收敛，human 插话只可能**延迟**（未冻结者
  多响应一轮），不可能**阻断**
- 延迟的上界：未冻结者配额有限（含 h_count 增量），耗尽后确定性 freezing

### 3.3 all-freezing 阶段（starter 启动 RR 前）

- starter 的 RR 启动检查 `has_new_messages_for_me` → human 消息 = 新消息 →
  **唤醒 LLM 读取 human 内容后再确定性写 pass**——现有"冻结期间新消息"
  逻辑天然覆盖（human 消息与普通新消息同路径）
- 轮转顺序不变（starter 仍是启动者）
- 其他 agent：等 starter 的 pass，不受影响

### 3.4 round-robin 阶段（含必须修复）

**现状**：`rr_next_speaker` 读 **bare HEAD 消息**的 `next` 字段（不变量：
HEAD 消息 = 最后发言者，next = 下一位；RR 串行，同一时刻只有 next 者写）。

**human 插话的破坏**：human 消息不携带 next。human 插话 commit 后
HEAD = `human/NNNN.md` → `rr_next_speaker` 读到无 next 的消息 → 返回 None
→ **轮转链断裂**（所有 agent 的 `nxt != agent`，无人响应，只能等 stall 超时
兜底——不能接受）。

**修复（信息层/流程层分离的直接推论）**：`rr_next_speaker` 跳过非参与者
消息——从 HEAD 开始逐 commit 往前找**最后一条参与者消息**，读它的 next。

```
rr_next_speaker（修改后）：
  rev-list HEAD 逐 commit（--name-only）
    若该 commit 的文件列表含参与者消息文件 → 读其 next，返回
    否则（human 消息 commit）→ 继续往前
```

**论证**：
- RR 串行不变量保持：human 不算发言者，最后发言者 = HEAD 之前的最后一条
  参与者消息，其 next 仍是正确轮转链
- human 消息在轮转链中"不存在"（跳过），但它作为信息仍被轮到的 agent
  读取（§3.4 下一条）
- 不变量更新为："**最近的参与者消息**的 next = 下一位"

**轮到的 agent 的行为**：`nxt == agent` 且 `has_new_messages_for_me`（
human 消息在 diff）→ 唤醒 LLM：读取 human 内容 + 照常写 pass（单向流）。
未轮到的 agent：`nxt != agent` → sleep。**轮转顺序、轮次计数、全员 pass
判定全部不变**。

**边界推演**：

| 场景 | 行为 | 正确性 |
|---|---|---|
| human 在 starter 的 pass 之后插话 | HEAD=human → rr_next_speaker 找到 starter 的 pass → next 正确 | ✅ |
| human 在轮次之间插话 | 同上，轮转链无感 | ✅ |
| human 连续插话 2 条 | 逐 commit 跳过 2 个 human commit | ✅ |
| human 插话后恰好轮到我 | 唤醒时多读一条内容，照常 pass | ✅ |
| human 在收尾判定瞬间插话 | 全员 pass 判定只看参与者（并发下 push 顺序决定）→ 正常 | ✅ |

### 3.5 收尾（result.md + concluded）

- 收尾触发（全员 pass / max_rr 兜底 / stall）判定只看参与者 → human 无关
- rw 写 result.md 期间 human 插话：rw 的 commit+push 与 human 并发 →
  现有 push 容错覆盖；result.md 内容由 LLM 写（是否引用 human 插话由
  LLM 判断——内容层自由）
- concluded 判定不受 human 影响

### 3.6 stall（无进展超时收尾）

- stall 判定 = 600s 无新 commit → **human 插话 = 新 commit = 重置 stall**
  （用户 2026-08-30 确认：保持自然语义，不改 stall 判定）
- 语义论证：human 插话是讨论的真实活动（agents 可能响应）——重置 stall
  是正确的（讨论确实"有进展"）
- 副作用：human 持续插话可无限推迟 stall 收尾——但这是 human 主动行为
  （人控制插话频率），且 human 插话不产生"流程义务"（agents 不响应也
  不阻塞），可接受

## 4. 配额语义

### 4.1 设计

```
配额耗尽判定：speak_count >= max_meeting + human_msg_count
（speak_count = 该 agent 的 mode=meeting 且 type=message 消息数，从 bare 重算）
（human_msg_count = bare 中 human/ 目录的消息数，从共享事实推导）
```

human 引发的 agent 响应**计入** speak_count（`_meeting_speak_count` 零改动）；
同时 human 每发一条消息，所有 agent 的配额上限 +1。

### 4.2 净效果论证

max_meeting=10，human 发 1 条（h_count=1 → 所有 agent 上限 11）：

| agent 行为 | speak_count | 配额上限 | 净效果 |
|---|---|---|---|
| 响应了 human（1 轮） | +1 | +1 | 净 0（不加快耗尽）✅ |
| 未响应 human | 0 | +1 | 可用轮 +1（讨论空间略增） |

**对称性**：对所有 agent 相同增量——既不清零、也不单独奖励响应者；
无需区分"响应 human 的消息"与普通消息（`in_reply_to` 不可靠，不需要）。

**优点**：
- 判定只改上限（`max_meeting` → `max_meeting + h_count`），一行改动
- h_count 从共享事实（bare 树）实时推导：无状态传递、崩溃安全、
  loop 重启后一致

### 4.3 边界语义

| 场景 | 行为 | 正确性 |
|---|---|---|
| human 插话后配额尽但未冻结 | ⑤.2 条件不满足（上限 +1）→ 响应 human | ✅ 设计意图（human 给回应机会） |
| human 插话后**已冻结** | 发言锁优先，不解冻 | ✅ 与"不解除冻结"一致 |
| human 在 RR 阶段插话 | meeting 配额不适用（RR 数 starter 的 RR 消息）→ 无影响 | ✅ |
| human 连续插话 k 条 | 上限 +k；agents 有 k 轮额外空间 | ✅ 讨论空间随插话量线性增长 |

### 4.4 链式响应的精确语义（重要澄清）

human 插话 → a 响应 → **a 的响应又触发 b**（普通消息链）→ b 响应 → …
这是 agents 之间本来就有的讨论机制，不是 human 专属路径。

**精确语义**："不加快配额耗尽"指——human 插话本身不消耗任何 agent 的
配额（每条 human 消息恰好补偿一轮直接响应）；但 human 插话**间接延长
讨论**（新话题 → agents 之间更多链式交锋）与 agents 主动发起新话题
无本质区别，链式消耗同样受配额上限约束（上限 = max_meeting + h_count，
链式超过增量部分照常耗尽 → 确定性 freezing）。

**结论**：human 插话对配额的影响 = 每条消息给全体 agent 各 +1 轮，
不多不少；链式讨论是 agents 自己的配额消费行为。

## 5. human 通道：viewer / sayer 两命令

### 5.1 架构（两个进程 + 壳可选）

human 通道 = **两个独立进程 + 壳**（用户 2026-08-30 定）：

```
┌──────────────────────────────────────────────┐
│ 壳（可选）：阶段 3 = 主 pi 的 TUI              │
│  消息区 ← human-viewer 的增量输出（tool output）│
│  输入区 → 用户插话 → human-sayer（tool/command）│
└──────────────┬───────────────────┬────────────┘
               │                   │
   ┌───────────▼───────┐   ┌───────▼───────────┐
   │ human-viewer      │   │ human-sayer       │
   │ 只读：bare → 新消息+ │   │ 文本 → human/NNNN.md  │
   │ 状态变化 → 文本流    │   │ → commit+push → 反馈  │
   └───────────────────┘   └───────────────────┘
```

- **viewer / sayer 互不相干**：viewer 只读 bare（无写路径、无 clone、
  无并发问题）；sayer 只写（不展示、不 poll）
- **壳是消费者**：阶段 1/2 无壳也能用（终端 `--follow` 看 + 命令插话）；
  阶段 3 skill 中主 pi 的 TUI 即壳（viewer → tool output 展示、
  sayer → tool 插话）——不另做 curses UI

### 5.1.1 tmux 双屏形态（**已放弃 2026-09-01**，用户决定）

曾作为辅助壳形态（上屏 `human_viewer --follow` / 下屏 `human_sayer -i`，
由 `/agents-helper-tmux` prompt 启动，实测验证通过）。**放弃原因**：主 pi
代理形态（默认模式）已成熟——观看走 `!!` 流式（零 token）、插话走扩展
（零 LLM），tmux 形态无独立价值；pi-web 等无终端场景本来就用不了。
`human_sayer -i` 交互模式**保留**（终端手动插话仍可用，无危害）。

### 5.1.2 默认模式（主通道，阶段 3 skill 核心）

**场景**：pi-web（外挂 web 接口替代 TUI）等无终端环境——tmux 不可用，
观看走 `!!` 流式通道；有终端时用户可直接本地跑 viewer。

```
主 pi（skill 流程）：
  1. start_discussion 创建+启动讨论
  2. 告知用户观看方式（viewer 全文不进 LLM，零 token）：
     - 有终端：python3 human_viewer.py <dir> --follow
     - pi-web：!!python3 human_viewer.py <dir> --follow
       （pi-web 的 !! 流式 bash 通道，实测验证 2026-08-31；Esc 中断，
       看与说交替）
  3. 轻量轮询：--status 直到 done/stopped（不 --view 转述全文）
  4. done → 读 result.md 总结 → 清理（--cleanup）
```

要点：
- **viewer 全文不进 LLM 上下文**（!! 的 excludeFromContext / 终端本地
  执行）——观看零 token，主 pi 不转述
- **插话独立命令**（`agents-helper-human` 扩展命令，用户
  2026-08-31 定）：零 LLM 参与——handler 直接 spawn human_sayer，
  notify 反馈；普通 user message 一律视为与主 pi 对话，不歧义；
  主 pi 不询问/不代发
- 主 pi 轮询只报状态（running/done/stopped），有新插话反馈才告知
- `--status` 轮询与观看并行：用户实时观看不受主 pi 轮询影响

### 5.2 human-viewer（阶段 1）

**定位**：只读观察工具——实时展示讨论进展（agents 的消息 + 状态变化）。

**入口**：`python3 human_viewer.py <base> [--since <ref>] [--follow]`

- 增量输出：`--since <ref>` 之后新 commit 中的消息（frontmatter + 正文）
  + 状态变化（mode 切换：meeting → all-freezing → round-robin → concluded）
- `--follow`：循环模式（tail -f 式）：自身维护游标（`<base>/.viewer-cursor`），
  每轮输出增量后 sleep（复用 POLL_INTERVAL），直到讨论 done（result.md +
  concluded）或 Ctrl-C
- 无 `--follow`：单次增量输出后退出（主 pi / skill 每轮调用此模式）
- **游标**：`--follow` 用文件游标（`<base>/.viewer-cursor`，记录已输出的
  commit/HEAD）；单次模式用 `--since` 参数（无状态，调用方传）
- **输出格式**（稳定文本契约，供壳/主 pi 消费）：

```
【状态】meeting
[a/0005] a (message)
正文……
---
[human/0001] human (message)
正文……
---
【状态】all-freezing
```

- **实现**：纯 bare 只读（git log/show/ls-tree 走 meeting_fs 只读函数）；
  状态变化 = core 聚合判定（复用 `_each_agent_messages` 思路读 bare 树）
- **讨论结束检测**：bare 树含 `type: concluded` → 输出【讨论已结束】+
  result.md 路径 → `--follow` 模式退出

**依赖**：meeting_core（聚合判定）、meeting_fs（只读 git）。无写路径。

### 5.3 human-sayer（阶段 2）

**定位**：插话命令——写入一条 human 消息。

**入口**：

```bash
python3 human_sayer.py <base> <文本>      # 单次插话（文本可多行：参数或 stdin）
python3 human_sayer.py <base> -i          # 交互模式（实测新增，用户 2026-08-31）
```

**交互模式 -i**（终端手动插话）：逐行累积、**空行 Enter 提交**、
Ctrl-D 退出——粘贴多行/打字统一语义（替换原 bracketed paste 方案：纯
文本通道无终端控制序列）；实测用户反馈驱动（下屏 shell 敲命令不直观
→ 输入即插话）。

**流程**：

```
1. 校验：讨论目录存在；bare 存在（未 cleanup）
2. flock work-human/.human.lock（防两个插话并发）
3. git_pull work-human（容错）
4. 读 bare：HEAD、聚合 mode（core）、human/ 现有消息数
5. 写 human/NNNN.md（NNNN = 现有数 + 1；frontmatter 见 §2.2）
6. commit（message = "human: <摘要>"）→ push（git_push 容错重试）
7. 输出反馈："已发送 human/0005"
```

**并发容错**：
- 两个 sayer 并发（主 pi + 用户手动）→ flock 串行化（同一 work-human）
- flock 排队后仍可能序号竞争（极端）→ push 非快进 → pull --rebase →
  **同名文件冲突**（human/0005.md 两端不同）→ rebase 失败 → 报错
  "插话冲突，请重试"（人工场景频率极低，不引入锁）
- 与 agents 并发 push → 现有 git_push 容错（pull --rebase → 重推）

**依赖**：work-human（setup 时创建，§5.4）、写消息核心模块（frontmatter
补全 + commit+push——与 CLI `--human-msg` 共用一份，不重复实现）。

### 5.4 setup 扩展

- `human` 保留名校验：`--agents` 拆分后 / spec/agents/ 文件名中含 `human`
  → 报错退出
- **work-human 创建**（阶段 2 已实现）：setup 在重建循环**之外**独立创建
  `work-human/`（clone + 仓库级 git 身份；无 agent 定义/pi-agent.json/
  AGENTS.md——human 无 LLM 身份；不启动 loop 进程）+ rmtree 幂等守卫。
  实测教训（2026-08-31）：放入 participants 重建循环内会每迭代 clone
  一次 → 第二个参与者起 `already exists`（wrapper --start 暴露）
- `--cleanup` 自然覆盖（删目录含 work-human）

## 6. 决策记录

### 6.1 用户已拍板

| 决策 | 内容 | 来源 |
|---|---|---|
| 定位 | 人不是参与者，不参与流程控制；只插话 | 用户 2026-08-30 |
| 触发 | human 插话可触发 agents 响应，响应不影响 meeting 状态 | 用户 2026-08-30 |
| RR | human 不参与轮转；消息仅影响 agents 可读内容 | 用户 2026-08-30 |
| 配额 | 响应计入配额；human 每发言一次所有 agent 配额 +1（不加快消耗） | 用户 2026-08-30 |
| 语义 | 状态机"视而不见"（显式跳过），非物理隔离 | 用户 2026-08-30 |
| stall | human 插话重置 stall（自然语义，不改判定） | 用户 2026-08-30 |
| 阶段 | 先核心脚本（阶段 1），调试通过后再 skill（阶段 2） | 用户 2026-08-30 |
| 通道 | human 通道 = viewer（展示）+ sayer（插话）两命令 + 壳可选 | 用户 2026-08-30 |
| 壳 | 阶段 3 主 pi TUI 即壳；不另做 curses UI | 用户 2026-08-30 |
| tmux 双屏 | 纳入设计：上 viewer --follow / 下 shell sayer；主 pi 启动 + 用户 attach；阶段 3 与主 pi 代理形态并存 | 用户 2026-08-30 |
| 输入 | 插话文本支持多行（粘贴场景）；shell 参数/文件通道 | 用户 2026-08-30 |
| 开发铁律 | 职责边界 / 复杂度匹配 / 设计符合度（每次修改后核验） | 用户 2026-08-09（沿用） |
| skill 名 | `agents-helper`（区别于源项目 meeting-discuss） | 用户 2026-08-31 |
| npm 包名 | `pi-agents-helper` | 用户 2026-08-31 |
| tmux 定位 | **辅助方法**：需用户可访问终端（pi-web 无终端时不可用） | 用户 2026-08-31 |
| 主通道 | **主 pi 代理形态**：skill 自己管理 viewer/sayer（轮询 + 插话），tmux 是辅助 | 用户 2026-08-31 |
| 下屏高度 | tmux 下屏固定 4 行（`split-window -v -l 4`） | 用户 2026-08-31 |
| 交互模式 | sayer `-i`：逐行累积、空行 Enter 提交、Ctrl-D 退出（下屏/主 pi 共用） | 用户 2026-08-31 实测反馈 |
| 多行提交 | 交互模式空行提交（替代 bracketed paste——纯文本通道，无终端控制序列） | 2026-08-31 实测定 |
| AGENTS.md.tpl | 已加「来自 human 的插话」节（权威输入语义） | 2026-08-30 定稿 |
| 插话入口 | 独立命令 `agents-helper-human`（扩展命令，零 LLM：handler spawn human_sayer + notify）；普通 user message = 与主 pi 对话 | 用户 2026-08-31 |
| 插话迁移 | agents-helper-human 演化：skill（args 追加歧义）→ prompt template（$1 替换无歧义，实测）→ extension 命令（零 LLM，2026-08-31 定） | 用户 2026-08-31 |
| 主 skill 形态 | 两 prompt + 一 extension（用户 2026-08-31 定）：agents-helper / agents-helper-tmux 迁到 prompt template（$1 = 主题机制性消除参数歧义——skill 的 args 追加靠措辞修补过两轮，实测仍脆弱）；agents-helper-human 已是 extension（零 LLM） | 用户 2026-08-31 |
| 等待机制化 | 主 pi 回合结束、零轮询（用户 2026-08-31 定）：用户用 !!viewer 观看（done 自动退出 = 完成信号）；主 pi 只在用户驱动时查一次 --status。废弃"提示词要求持续轮询"（实测 LLM 违反两次：提示词控制不可靠） | 用户 2026-08-31 |
| 观看命令输出 | wrapper --start 输出完整 `!!python3 ... --follow` 命令（含路径），主 pi 原样展示供复制 | 用户 2026-08-31 |
| 讨论目录发现 | 方案 3（用户 2026-08-31 定）：零状态文件——wrapper 目录名 = discuss-<PI_SESSION_ID>-<时间戳>（aft 不再替换 bash 后 PI_SESSION_ID 注入可用）；扩展用 ctx.sessionManager.getSessionId() + glob cwd/discuss-<sid>-* 取最新；session 隔离彻底（同目录多 session 也互不干扰）。历程：全局文件 → 项目下文件（aft 替换 bash 时代，sid 拿不到）→ cwd+sid 推导 | 用户 2026-08-31 |
| models.md 读取 | 环境变量优先（PI_PROVIDER/PI_MODEL/PI_REASONING_LEVEL，aft 改动后可用的当前生效值），session 文件解析降为兜底 | 用户 2026-08-31 |
| agents 参数化 | prompt 第二参数 $2 = agents 数量（默认 3）；wrapper --prepare --agents（名称列表 "a,b,c" 或纯数字 "4"→a..<n>，上限 26，默认 DEFAULT_AGENTS）；question.md 立场行/models.md/agents/*.md/.order 四处按列表循环；human 保留名校验在 wrapper；立场行 printf 以 - 开头被当选项 → printf '%b'（实测暴露） | 用户 2026-09-01 |
| 路径方案 | 固定路径（用户 2026-09-01 定）：prompt 引用 wrapper/规范/viewer 用固定路径 ~/.pi/agent/npm/node_modules/pi-agents-helper/...（pi install 用户级安装路径固定，零脚本零副本；只支持用户级安装，项目级不支持）；开发机建 symlink 指向仓库。postinstall 渲染否决（副本生命周期=新持久状态+事实源分裂+开发机分叉+脚本环境依赖）；工具方案否决（LLM 多一步流程控制，用户不希望依赖 LLM 控制流程） | 用户 2026-09-01 |
| tmux 入口 | 独立 skill `agents-helper-tmux`：用户明确指定才用，之后操作全在 tmux 内 | 用户 2026-08-31 |
| 放弃 tmux | **整个 tmux 形态放弃（2026-09-01）**：删 prompts/agents-helper-tmux.md；主 pi 代理形态已成熟（!! 流式观看 + 扩展插话），tmux 无独立价值。human_sayer -i 交互模式保留（终端手动插话无害）；README/AGENTS.md/背景规范引用同步清理。决策记录历史条目（tmux 双屏/定位/下屏高度/入口）保留为历史 | 用户 2026-09-01 |
| 两 prompt 拆分背景提炼 | **agents-helper-prepare + agents-helper 两步**（用户 2026-09-02 定）：背景提炼（LLM 思考型）与启动讨论（流程型）分离，各自单一职责——解决「提炼变重会干扰 skill 流程」；prepare 产 discuss_prepare_<sid>.md（当前目录，含主题+背景，sid 用 PI_SESSION_ID）；cleanup 删同 sid 文件（不变式：cleanup 后无 prepare 文件，机制判断非 LLM 判断）；第一步审核 spec 时手动复制背景进 background.md，全流程自动化（wrapper 读文件）待后续；文件格式若 LLM 漂移则脚本化（--save-prepare，LLM 只传内容） | 用户 2026-09-02 || aft/magic-context 屏蔽机制纠错 | **work settings.json 屏蔽写法两次纠错（2026-09-03，实测驱动）**：① 原 `{source, autoload:false}` 无资源 patterns = pi delta 空操作（用户级包照常全量加载——aft 进程照常 spawn，top 可见）；② 无 autoload:false 的资源 `[]` 形态 = project wins → pi 为每个 work 项目级 npm install（4 次 install magic-context 实测暴露）。正确写法（pi config 权威）：`{source, autoload:false, extensions:["-dist/index.js"]}`——project delta 逐文件禁用（两包各只有 1 个扩展文件），不装项目副本、aft 不 spawn、其它扩展保留。另修复：settings 写入遍历 agents 硬编码 a b c（--agents 参数化后漏写 work-d）→ 改读 spec .order | 用户 2026-09-03 |
| pi-web 观看 | `!!human_viewer.py <dir> --follow` 流式实时（excludeFromContext，不进 LLM）；Esc 中断看说交替 | 用户 2026-08-31 改 pi-web + 实测 |
| 主 pi 轮询 | 只报状态不转述全文；观看零 token | 用户 2026-08-31 |

### 6.2 待确认

（已全部解决，无遗留）

## 7. 测试策略

| 层 | 内容 |
|---|---|
| 单元 | 配额增量判定（h_count=0/k）、rr_next_speaker 跳过（HEAD=human/中间/连续）、human_msg_count 计数、保留名校验、viewer 增量输出（--since）、sayer frontmatter 生成 |
| FakeAgent 多进程 | 带 human 插话的完整讨论：meeting 插话触发响应、RR 插话轮转不断、收敛正常 |
| 边界 | 冻结中插话不解冻、RR 中插话不断链、配额尽未冻结者获回应机会、连续插话 k 条、human+agent 并发写 |
| 回归 | 基线全部测试不改语义仍绿（human 功能是纯增量） |

## 8. 阶段划分（全部完成）

| 阶段 | 内容 | 状态 |
|---|---|---|
| **1** | human-viewer（只读展示：新消息 + 状态变化，增量/--follow/游标）+ rr_next_speaker 修复 + 配额增量 + 保留名校验 + 测试 | ✅ `stage1-human-viewer` |
| **2** | human-sayer（插话：写消息核心 + work-human + flock + commit+push 容错）+ 交互模式 -i + 测试 | ✅ `stage2-human-sayer` |
| **3** | skill 层——SKILL.md（agents-helper）、discuss.sh wrapper（--view/--say）、npm 包装（pi-agents-helper）；主 pi 代理形态（主通道）+ tmux 双屏（辅助） | ✅ `stage3-skill` |

## 9. 风险与已知边界

| 风险 | 分析 |
|---|---|
| LLM 对 human 消息过度服从 | human 消息进 prompt 后 LLM 可能当"指令"——内容层自由，无法也不应强制；流程层不受影响（它必须写合法消息，协议仍确定性） |
| human 消息体量 | 长文本进 prompt 占 token——human 消息与普通消息同规则（可读），无特殊上限；阶段 3 skill 可提示用户精简 |
| 讨论被 human 插话无限延长 | 触发仅限未冻结配额内 agent；配额上限随 h_count 线性增长——human 持续插话确实持续延长讨论，这是 human 主动行为的合理结果 |
| work-human 与参与者隔离失效 | 唯一风险点是 `_each_agent_messages` 等遍历用 agents 列表而非目录扫描——现有实现即列表遍历，无需改 |

## 10. 评估 pi 机制的方法论（讨论产出，2026-08-31 入档）

2026-08-31 以"subagent 对本项目参考价值"为题的讨论（discuss-20260831-095814，
含 human 插话）收敛出的评估姿势，今后评估任何 pi 机制固定沿用：

1. **按需求域对照，而非功能列表对照**——subagent 不做持久化不是"少做了"，
   而是它根本没面对该需求（调用-返回式）；评估前先问"它解决什么问题、
   我们解决什么问题"，而非"能不能抄"。
2. **同底座看上层差异**（human 插话贡献）——subagent 与 meeting_loop 共享
   同一底层（`pi --mode json` + append-system-prompt），差异全在上层：
   `--no-session` 无状态 vs 会话持久化（崩溃可恢复、human 随时插话）、
   stdout 事件流 vs git 消息文件（可审计、断点续议）、无工具防护 vs
   `.git.locked`（无主控模型没有监督者，防护必须内建进流程层）。底层相同
   不等于可借鉴，差异在哪一层、为什么存在，才是判断依据。
3. **无主控定位的防护必然性**——监督模型下的"无防护"不能反推我们的防护
   是过度设计；无主控内建防护是定位的必然组成。

**pending 项**（讨论标记，需求驱动再做）：
- usage 聚合展示：数据源实证 `pi-sessions/*.jsonl` 每行含完整 usage
  （totalTokens + cost），viewer 只读聚合即可，无新采集依赖；属信息层
  旁路展示，不进 protocol.json。落地前须先验证 pi 对 prompt_file
  frontmatter 的剥离语义（未验证，若原样拼入会残留 `---` 文本）。
