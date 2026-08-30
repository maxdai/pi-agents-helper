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
├── templates/               # 配置模板（AGENTS.md / agent 定义 / gitignore / spec）
├── tests/                   # 测试套件（unittest discover tests）
└── docs/pi-helper-design.md # 设计文档
```

## 快速开始

```bash
# 1. 创建并启动一个 2-agent 讨论
python3 start_discussion.py --dir mydisc \
  --agents a,b \
  --topic "设计一个轻量任务队列的消息字段清单" \
  --pure --start

# 2. 观看讨论（tmux 双屏：上屏实时展示，下屏 4 行插话输入）
tmux new-session -s discuss-mydisc "python3 human_viewer.py discussion-mydisc --follow"
tmux split-window -v -l 4 "python3 human_sayer.py discussion-mydisc -i"

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

### tmux 双屏形态（实测验证）

```
┌────────────────────────────────┐
│ 上屏：human_viewer --follow     │  ← 新消息/状态变化实时展示，done 自动退出
├────────────────────────────────┤
│ 下屏（4 行）：human_sayer -i    │  ← 输入即插话（空行提交）
└────────────────────────────────┘
```

主 pi 可一键启动 tmux session（`discuss-<时间戳>`），用户在任何终端
`tmux attach -t <名字>` 直接观看/插话，随时 detach（讨论继续）。

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

## 依赖与平台

| 依赖 | 版本 | 用途 |
|---|---|---|
| Python | ≥3.9 | 脚本运行时（标准库，无第三方包） |
| pi | 已安装的 pi CLI | 讨论 agent 运行时 |
| git | 任意 | bare 仓库 + 每 commit 一条消息 |
| tmux | 任意 | 可选：双屏观看/插话形态 |
| Linux | — | `pgrep`、`setsid`、`fcntl.flock` |
