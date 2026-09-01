# pi-agents-helper —— 带 human 插话通道的 Pi 多 agent 讨论工具

衍生自 [`pi-agents-meeting-discuss`](https://github.com/maxdai/pi-agents-meeting-discuss)：
保持原有的**多 agent 会议式讨论协议完全不变**（n 个 LLM agents 通过共享 git
仓库自由讨论 → 冻结级联 → 轮转收尾 → 共识结论），**额外附加一个"人的插话"
通道**：人不是参与者、不参与流程控制，只是可以向讨论注入信息，agents 能看到
并（可选地）回应。

**核心设计：信息层与流程层分离**——human 消息只影响"agents 能读到什么"，
状态机对它的判定"视而不见"（显式过滤）：不参与冻结/轮转/收尾判定、不参与
轮转链、不加快配额消耗。human 完全不插话时，讨论与原系统行为完全一致。

## 目录结构

```
pi-agents-helper/
├── start_discussion.py      # 主脚本（创建 / 启动 / 状态 / 等待 / 清理）
├── meeting_engine.py        # 唯一状态机（meeting→af→RR→result）
├── meeting_core.py          # 纯逻辑判定（无 I/O）
├── meeting_fs.py            # git/文件 I/O 层
├── meeting_loop.py          # 真实 LLM 薄壳（responder = 唤醒 pi）
├── fake_agent.py            # 测试薄壳（responder = 随机决策）
├── human_viewer.py          # 【human 通道】只读展示讨论进展
├── human_sayer.py           # 【human 通道】插话命令（含交互模式 -i）
├── scripts/discuss.sh       # skill wrapper（prepare/start/status/wait/cleanup/view/say）
├── skills/                  # 三个 skill（agents-helper / -tmux / -human）
├── package.json             # npm 包 pi-agents-helper（pi.skills: ["./skills"]）
├── templates/               # 配置模板（AGENTS.md / agent 定义 / gitignore / spec）
├── tests/                   # 测试套件（unittest discover tests）
├── AGENTS.md                # 项目开发指南（核心规则与结构）
└── docs/pi-helper-design.md # 设计文档
```

## 快速开始

### 安装（官方方式：pi install 用户级）

```bash
pi install npm:pi-agents-helper
```

- 包装到固定路径 `~/.pi/agent/npm/node_modules/pi-agents-helper/`，prompt/扩展
  从包加载（无需复制到 `~/.pi/agent/prompts/` 等目录）
- **只支持用户级安装**（项目级 `.pi/npm/` 不支持——prompt 引用的是用户级
  固定路径）
- reload 后生效：`/agents-helper`、`/agents-helper-tmux`、`/agents-helper-human`
- 开发仓库场景：建 symlink 使固定路径指向仓库
  （`ln -sfn /root/pi-agents-helper ~/.pi/agent/npm/node_modules/pi-agents-helper`）

### 用 skill（推荐，主 pi 会话内）

```
/agents-helper "<问题>" [agents 数量]        # 默认模式启动讨论（pi-web 也可用）
/agents-helper-tmux "<问题>" [agents 数量]      # tmux 双屏模式（用户明确指定）
/agents-helper-human "<文本>"                  # 讨论中插话（agents 可见可回应）
```

### 用命令行（直接操作）

```bash
# 1. 创建并启动一个 2-agent 讨论
python3 start_discussion.py --dir mydisc \
  --agents a,b \
  --topic "设计一个轻量任务队列的消息字段清单" \
  --pure --start

# 2. 观看讨论（全文实时滚动，不进 LLM）：任何终端
python3 human_viewer.py discussion-mydisc --follow

# 3. 阻塞等待完成，打印 result.md 路径
python3 start_discussion.py --dir mydisc --wait

# 4. 清理（先保存 result.md 到父级，再删目录）
python3 start_discussion.py --dir mydisc --cleanup
```

## human 通道

human 不是参与者（`human` 是保留名，不可作为 `--agents` 传入），固定附加、
另算。通道由两个独立命令组成，互不相干：

### human-viewer（展示，只读）

```bash
python3 human_viewer.py <base>                  # 当前状态 + 全部消息
python3 human_viewer.py <base> --since <ref>    # 增量（ref 之后）
python3 human_viewer.py <base> --follow         # 循环展示直到讨论结束
```

输出契约（供壳/主 pi 消费）：`【状态】<mode>` + 消息（`[作者/序号] from (type): summary` + 正文），讨论 done 时打印 result.md 路径并退出。

### human-sayer（插话，写）

```bash
python3 human_sayer.py <base> "插话文本"              # 单次插话
echo "多行文本" | python3 human_sayer.py <base>       # stdin 多行
python3 human_sayer.py <base> -i                      # 交互模式（tmux 下屏推荐）
```

交互模式：逐行累积、**空行 Enter 提交**、Ctrl-D 退出——输入即插话，无需命令行。

插话效果：agents 下次轮询即看到（触发响应）；已冻结 agent 不响应（发言锁）；
human 每插话一次，所有 agent 的 meeting 配额上限 +1（响应不加快配额耗尽）。

### tmux 双屏形态（实测验证；由 agents-helper-tmux prompt 启动）

```
┌────────────────────────────────┐
│ 上屏：human_viewer --follow     │  ← 新消息/状态变化实时展示，done 自动退出
├────────────────────────────────┤
│ 下屏（4 行）：human_sayer -i    │  ← 输入即插话（空行提交）
└────────────────────────────────┘
```

**用户明确指定才用**（`/agents-helper-tmux`）：tmux 需要终端访问，
pi-web 等无终端场景不可用。主 pi 一键启动 tmux session（`discuss-<时间戳>`）
并提示 attach 命令；用户 attach 后观看/插话全在 tmux 内进行，随时 detach
（讨论继续），主 pi 只轻量轮询等在 done 收尾。

## 参数详解（start_discussion.py）

| 参数 | 条件 | 默认 | 说明 |
|---|---|---|---|
| `--dir <name>` | 除 `--spec-gen` 外需要 | — | 讨论目录：含 `/` `~` `.` 等路径符 → 直接作为完整路径；否则 → 在 cwd 下创建 `discussion-<name>/` |
| `--topic <text>` | 创建且非 `--spec` 时需要 | — | 讨论主题 |
| `--agents <a,b>` | — | `a,b` | agent 名单，逗号分隔，**任意数量 ≥2**（`human` 是保留名） |
| `--stances <json>` | — | 无 | 各方初始立场，JSON 对象 |
| `--models <json>` | — | 默认模型 | 各 agent 模型，JSON 对象 `{"a": "provider/model", ...}` |
| `--max-meeting <n>` | — | 10 | meeting 阶段每 agent 发言配额 |
| `--max-rr <n>` | — | 7 | RR 阶段轮次配额 |
| `--background <text>` | — | 无 | 讨论背景（AGENTS.md 的「背景」节） |
| `--questions <Q1\|Q2>` | — | 无 | 待回答问题列表 |
| `--pure` | — | 关 | 创建时固化：唤醒 pi 时关闭外部加载 |
| `--result-writer <name>` | — | 最后一位 | 谁生成 result.md |
| `--start` | — | 关 | 生成后立即启动讨论循环 |
| `--skip-setup` | — | 关 | 跳过环境生成，只启动已有环境 |
| `--status` / `--wait` / `--cleanup` | — | 关 | 状态 / 阻塞等待 / 清理 |
| `--spec-gen <dir>` / `--spec <dir>` | — | 无 | spec 规格目录（内容源，与内容参数互斥） |

## 讨论机制（双阶段协议）

```
meeting（自由发言）→ all-freezing（冻结级联）→ round-robin（RR 收尾）→ result
```

- 状态判定 = 聚合所有 agent 最后一条消息（bare 树），与 human 消息无关
- LLM 只提供内容；协议字段/信号/判定全部由 loop 确定性完成
- 每 commit 一条消息：`git log` 即讨论史
- 无静默铁律：被唤醒必产出，无产出 loop 重试 + 代写
- human 插话不推动也不阻塞流程（信息层/流程层分离）

## 设计文档

- `docs/pi-helper-design.md`：完整设计（信息层/流程层分离、各阶段行为推演、
  配额语义、viewer/sayer 设计、tmux 形态、测试策略、决策记录）

## 入口用法（两 prompt + 一 extension）

npm 包 `pi-agents-helper` 提供两个 prompt template 与一个扩展命令（**用户手动触发**）：

| 入口 | 形态 | 用途 | 观看方式 |
|---|---|---|---|
| `/agents-helper "<问题>" [agents 数量]` | prompt | **默认模式**（pi-web/无终端可用）；`agents 数量` 可选（默认 3，数字或名称列表） | 本地 viewer（见下），观看不进 LLM（零 token） |
| `/agents-helper-tmux "<问题>" [agents 数量]` | prompt | **tmux 双屏模式**（用户明确指定）；`agents 数量` 可选 | tmux 上屏实时全文 + 下屏插话，观看/插话全在 tmux 内 |
| `/agents-helper-human "<文本>"` | extension | **插话**（讨论进行中） | —（一条消息，立即发送） |

讨论进行中，普通 user message 一律视为与主 pi 对话；插话请用
`/agents-helper-human`（扩展命令，零 LLM 直接执行）。

### 观看方式（viewer 全文不进 LLM）

```bash
# 有终端：任何终端实时滚动
python3 human_viewer.py <目录> --follow

# pi-web：!! 流式（excludeFromContext，不进 LLM；Esc 中断后插话再续看）
!!python3 ~/.pi/agent/npm/node_modules/pi-agents-helper/human_viewer.py <目录> --follow
```

### 主 pi 流程（默认模式，prompt 详述）

1. `discuss.sh --prepare "<问题>" [--agents ...] --background "<背景>"` → 主 pi **提炼当前对话中相关背景**写入 background，生成 spec（继承主 pi model/thinking）；**展示 spec 请用户查看/编辑**（background.md 可修改），确认后继续
2. 用户确认后 `discuss.sh --start <spec>` → 讨论启动，输出讨论目录 + **完整 `!!` 观看命令**（用户复制执行）
3. **主 pi 结束回合**（不轮询、不等待）——用户通过 `!!` 观看，viewer 在讨论 done 时自动退出；用户说"结束了"或询问时主 pi 查一次 `--status`
4. `done` → 读 `<目录>/work-c/result.md` → 向用户摘要
5. `discuss.sh --cleanup <目录>`（必须，避免残留 session）

wrapper 命令一览：

```bash
./scripts/discuss.sh --prepare "<问题>" [--agents "4"|"x,y"] [--background "<背景>"]  # 生成 spec
./scripts/discuss.sh --start <spec目录>                          # 创建+启动（agents 从 spec 读）
./scripts/discuss.sh --status <目录> | --wait <目录> | --cleanup <目录>
./scripts/discuss.sh --view <目录> [--since <ref>]               # 增量查看（末尾输出 HEAD= 游标）
./scripts/discuss.sh --say <目录> "<文本>"                        # 插话
```

默认参数：agents=`a,b,c`（`--prepare --agents 4` 生成 a..d；`--agents "x,y"` 自定义名称；
`human` 是保留名）、`--max-meeting 10`、`--max-rr 5`；子讨论 agents 禁用
`magic-context`/`aft` 扩展（项目级 `.pi/settings.json`）。

## 依赖与平台

| 依赖 | 版本 | 用途 |
|---|---|---|
| Python | ≥3.9 | 脚本运行时（标准库，无第三方包） |
| pi | 已安装的 pi CLI | 讨论 agent 运行时 |
| git | 任意 | bare 仓库 + 每 commit 一条消息 |
| tmux | 任意 | 可选：双屏观看/插话形态 |
| Linux | — | `pgrep`、`setsid`、`fcntl.flock` |

## 环境要求：aft 的 bash 配置（重要）

**必须配置**：`~/.config/cortexkit/aft.jsonc` 中设置 `"bash": false`

```jsonc
{
  "semantic_search": true,
  "search_index": true,
  "bash": false
}
```

**原因**：本工具依赖 pi 向 bash 工具注入的会话环境变量
（`PI_SESSION_ID` / `PI_PROVIDER` / `PI_MODEL` / `PI_REASONING_LEVEL`）：

- `PI_SESSION_ID` → 讨论目录命名含 session id，`/agents-helper-human`
  扩展按 sid 自动发现当前讨论目录（零状态文件、session 隔离）
- `PI_PROVIDER` / `PI_MODEL` / `PI_REASONING_LEVEL` → spec 的 `models.md`
  继承主 pi 当前模型与思考强度

aft 默认会接管（重写）bash 工具，接管后这些变量**不再注入**（环境变量
只注入原生 bash，不注入 aft 重写后的调用）——插话扩展将找不到讨论目录，
models.md 退化为兜底值。

**检查**：`discuss.sh` 在 `--prepare`/`--start` 时自动检查该配置，未设置
会给出醒目警告（含修复方法）。此时插话扩展自动降级：找不到
`discuss-<sid>-*` 目录时回退到项目下最新 `discuss-*` 讨论（提示
"未按 session 隔离"），功能仍可用。配置后重启 pi 会话生效。
