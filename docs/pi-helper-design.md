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
- 只启动 n 个参与者 loop 进程；human **无 loop 进程**，插话由外部工具
  （human writer）单次触发
- setup 额外建 `work-human/` clone——仅作 human writer 的提交通道

### 2.2 消息语义（frontmatter）

human 消息 frontmatter 由 human writer 确定性补全，人只提供正文：

```
from: human
type: message          # 强制——人不写流程信号（freezing/pass/af/concluded）
mode: <写入时当前聚合 mode>   # 语义正确性；不参与判定（聚合只看参与者）
seen_at: <写入时 HEAD>       # 语义 = 人看到了当前全部状态（与 LLM 消息一致）
to: all
summary: <一句话摘要>        # 可选
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
| `_meeting_speak_count` | 参与者消息数（mode=meeting, type=message） | ⚠️ 计数不含 human；配额上限 +h_count（§5） |
| `rr_active_count` | starter 的 RR 消息数 | ❌ |
| 触发判定 `has_new_messages_for_me` | diff 范围的新消息 | ✅ **唯一参与点**（from=human → 触发响应） |
| stall 判定（HEAD 变化） | bare HEAD | ⚠️ human 插话 = HEAD 变化 = 重置 stall（§3.6） |
| `_stall_elapsed` 的"讨论已开始" | bare 是否存在消息文件 | ✅ human 消息也算讨论开始（讨论确实开始了） |
| `--status` 的 done 判定 | result.md + concluded | ❌ |

**结论**：human 消息在流程层只经过两个"缝隙"——触发判定（设计意图，§3.1）
和 stall 重置（自然语义，§3.6）；其余全部显式隔离。

## 3. 状态机逐分支推演

背景：`agent_loop` 每轮 = `git_pull → 读 bare 全量消息 → core 聚合判定 → 分派`。
以下逐分支分析 human 插话的行为。**前提**：human 插话 = human writer 完成
一次 commit+push（`human/NNNN.md` 进入 bare，HEAD 前移）。

### 3.1 meeting 阶段

**触发链**：human 插话 → 各 agent 的 `new_messages_with_meta` 的 diff
（`seen_at..HEAD`）包含 `human/NNNN.md` → `has_new_messages_for_me`（
from=human ≠ agent，to=all）→ **True** → 唤醒 LLM，human 消息进入 prompt。

**响应条件**（与普通消息完全一致的分支顺序）：

| agent 状态 | 行为 |
|---|---|
| 配额内 且 未冻结 | 唤醒响应（message/freezing） |
| 配额耗尽（未冻结） | ⑤.2 分支：因 h_count 配额增量可能不再耗尽（§5.3）→ 响应；否则确定性 freezing |
| 已冻结（发言锁） | **不响应**（⑤.4 锁优先）→ 冻结状态不被解除 |
| 唯一未冻结者（无新消息时） | human 消息存在 → triggered=True → 先响应 human，不自动冻结 |

**关键语义**：
- human 插话**不解除冻结**（发言锁优先，与"human 不干预流程"一致）
- 冻结级联判定只看参与者最后一条——human 插话不推动也不阻塞级联
- agent 对 human 的响应 = **普通发言**（与 agent 主动发言无区别）：它改变
  该 agent 自己的 last type、计入配额、可能触发其他 agent（链式，§5.4）——
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
- 语义论证：human 插话是讨论的真实活动（agents 可能响应）——重置 stall
  是正确的（讨论确实"有进展"）
- 副作用：human 持续插话可无限推迟 stall 收尾——但这是 human 主动行为
  （人控制插话频率），且 human 插话不产生"流程义务"（agents 不响应也
  不阻塞），可接受
- **待确认**：若用户认为 human 插话不应重置 stall（严格"不参与监测"），
  需改 stall 判定忽略 human 目录的 commit——复杂度上升，默认不这么做

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

## 5. 实现设计（阶段 1）

### 5.1 human writer（新增）

**入口**：`start_discussion.py --dir <dir> --human-msg <文本>`（单次操作，
与 `--status`/`--wait` 同模式；不启动任何进程）。

**流程**：

```
1. 校验：讨论目录存在；bare 存在（未 cleanup）
2. pull work-human（git_pull 容错）
3. 读 bare：HEAD、聚合 mode（core_aggregate_mode）、human/ 现有消息数
4. 写 human/NNNN.md（NNNN = 现有数 + 1；frontmatter 见 §2.2）
5. commit（消息体 = "human: <摘要>"）
6. push（git_push 容错重试）
```

**并发容错**：两个 human writer 同时插话（主 pi + 用户手动）→ 都数出
同一序号 → 先 push 成功，后 push 非快进 → pull --rebase → **同名文件
冲突**（human/0005.md 两端内容不同）→ rebase 失败。处理：捕获 rebase
失败 → 报错"插话冲突，请重试"（人工场景频率极低，不引入锁）。
**备选**：writer 写前在 work-human 加互斥文件（flock）——同一仓库内
串行；跨仓库无法防（同一 bare 只有 work-human 一个写入口，flock 足够）。
→ 采用 flock（work-human/.human.lock），rebase 冲突路径仍保留报错兜底。

**frontmatter 生成**：writer 内部断言完整性（from/type/mode/seen_at/to
齐全）——与 LLM 路径的 `validate_and_fix` 职责对齐（writer 自己保证
确定性补全，不走 responder 路径）。

### 5.2 work-human（setup 扩展）

```
work-human/
├── human/            # 消息目录
├── .git              # clone（git 身份：仓库级 config，含重建段）
└── protocol.json     # 可选（供 writer 读 participants/配额）
```

- **不启动 loop 进程**（无 `loop-human.log`、无 `status-human.json`）
- 参与者的 `_each_agent_messages` 遍历 agents 列表——human 不在其中，
  天然隔离
- `.gitignore`（讨论目录版）已忽略 work-* 各自文件？——核对：gitignore.tpl
  忽略运行时文件，human/ 消息需提交（与参与者消息同规则）

### 5.3 rr_next_speaker 修改（meeting_engine.py）

见 §3.4：rev-list 逐 commit 找最后一条参与者消息。实现要点：
- 参与者消息判定 = 文件名 `^<participant>/\d{4}\.md$`（participant ∈
  protocol.json 的 participants）
- 不变量注释更新："最近的参与者消息的 next = 下一位"
- 单测：human 消息在 HEAD / 中间 / 连续多条

### 5.4 配额判定修改（meeting_engine.py）

- 新增 `human_msg_count(bare)`：ls-tree 过滤 `^human/\d{4}\.md$` 计数
  （与 `_each_agent_messages` 同源，一次 ls-tree 可复用）
- ⑤.2 配额耗尽分支：`speak_count >= max_meeting + human_msg_count`
- 判定只看参与者 + h_count 作为配额增量的不变式保持

### 5.5 setup 扩展（start_discussion.py）

- `human` 保留名校验：`--agents` 拆分后 / spec/agents/ 文件名中
  含 `human` → 报错退出
- 额外创建 `work-human/`（复用 clone 逻辑，跳过 agent 定义/pi-agent.json/
  AGENTS.md.tpl——human 无 LLM 身份；question.md/protocol.json 可复制）
- `--cleanup` 自然覆盖（删目录含 work-human）

### 5.6 CLI 设计

```
python3 start_discussion.py --dir mymeet --human-msg "内容"
```

- 与 `--status`/`--wait` 并列的单次操作模式
- 可选 `--human-msg-file <path>`：长文本走文件（阶段 2 skill 用；
  阶段 1 先只做 `--human-msg`，按需再加）
- 摘要：`--human-msg` 时自动截取首行/前 N 字符作为 summary（可再定）

## 6. 决策记录

### 6.1 用户已拍板

| 决策 | 内容 | 来源 |
|---|---|---|
| 定位 | 人不是参与者，不参与流程控制；只插话 | 用户 2026-08-30 |
| 触发 | human 插话可触发 agents 响应，响应不影响 meeting 状态 | 用户 2026-08-30 |
| RR | human 不参与轮转；消息仅影响 agents 可读内容 | 用户 2026-08-30 |
| 配额 | 响应计入配额；human 每发言一次所有 agent 配额 +1（不加快消耗） | 用户 2026-08-30 |
| 语义 | 状态机"视而不见"（显式跳过），非物理隔离 | 用户 2026-08-30 |
| 阶段 | 先核心脚本（阶段 1），调试通过后再 skill（阶段 2） | 用户 2026-08-30 |
| 开发铁律 | 职责边界 / 复杂度匹配 / 设计符合度（每次修改后核验） | 用户 2026-08-09（沿用） |

### 6.2 待确认

| 问题 | 选项 | 我的倾向 |
|---|---|---|
| stall 是否被 human 插话重置 | a) 重置（自然语义） b) 忽略 human commit | a（§3.6） |
| `--human-msg-file` 是否阶段 1 就做 | a) 只 `--human-msg` b) 同时做 | a（按需再加） |
| AGENTS.md.tpl 是否加一句 human 说明 | a) 加（"可能收到 from: human 的插话，正常回应"） b) 不加 | a（降低 LLM 困惑） |
| human 消息的 summary 生成 | a) 自动截取 b) 可选参数 c) 不写 | a |

## 7. 测试策略

| 层 | 内容 |
|---|---|
| 单元 | 配额增量判定（h_count=0/k）、rr_next_speaker 跳过（HEAD=human/中间/连续）、human_msg_count 计数、保留名校验、writer frontmatter 生成 |
| FakeAgent 多进程 | 带 human 插话的完整讨论：meeting 插话触发响应、RR 插话轮转不断、收敛正常 |
| 边界 | 冻结中插话不解冻、RR 中插话不断链、配额尽未冻结者获回应机会、连续插话 k 条、human+agent 并发写 |
| 回归 | 基线全部测试不改语义仍绿（human 功能是纯增量） |

## 8. 阶段划分

- **阶段 1（当前）**：核心脚本功能（§5）+ 测试调试（§7）
- **阶段 2（调试通过后）**：skill 层——SKILL.md、discuss.sh wrapper、
  npm 包装、主 pi 插话入口（用户通过主 pi 会话插话，走 `--human-msg`）

## 9. 风险与已知边界

| 风险 | 分析 |
|---|---|
| LLM 对 human 消息过度服从 | human 消息进 prompt 后 LLM 可能当"指令"——内容层自由，无法也不应强制；流程层不受影响（它必须写合法消息，协议仍确定性） |
| human 消息体量 | 长文本进 prompt 占 token——human 消息与普通消息同规则（可读），无特殊上限；阶段 2 skill 可提示用户精简 |
| 讨论被 human 插话无限延长 | 触发仅限未冻结配额内 agent；配额上限随 h_count 线性增长——human 持续插话确实持续延长讨论，这是 human 主动行为的合理结果 |
| work-human 与参与者隔离失效 | 唯一风险点是 `_each_agent_messages` 等遍历用 agents 列表而非目录扫描——现有实现即列表遍历，无需改 |
