# pi-agents-helper 开发指南

> 本文件指导**本项目本身的开发**。与 `templates/AGENTS.md.tpl`（运行时参与讨论
> 的 LLM 行为指令）是两回事。

## 项目目的

在 `pi-agents-meeting-discuss`（Pi 版 meeting 多 agent 讨论协议）之上，增加
**human 插话通道**：人不是参与者、不参与流程控制，只是向讨论注入信息，
agents 可读并（可选地）回应。原讨论逻辑流程完全不变。

## 架构

```
meeting_core.py      纯逻辑判定——无 I/O（判定只看参与者，human 视而不见）
meeting_fs.py        git/文件层
meeting_engine.py    【唯一状态机】+ 协议信号 + responder 注入
meeting_loop.py      Pi 薄壳：responder = wake_llm（真实 LLM）
fake_agent.py        测试薄壳：responder = 随机决策
start_discussion.py  环境生成/启动/清理 + human writer
templates/           AGENTS.md.tpl / agent.md.tpl / gitignore.tpl / spec-readme.md.tpl
tests/               测试（unittest discover tests）
```

**核心不变式**：状态机只在 `meeting_engine.agent_loop` 一份；fake_agent 与
meeting_loop 通过注入 responder 复用。human 插话不改变状态机——只在
判定函数的**输入过滤**与**配额增量**两处扩展。

## 开发铁律（每次修改代码后必核验三条，用户要求 2026-08-09）

1. **职责边界**：各部件是否只做自己该做的任务，而没有在做别的部件
   本应负责的任务（LLM 内容 / 引擎流程 / fs I/O / core 纯逻辑 / human writer 写消息）
2. **复杂度匹配**：各部分代码复杂度是否符合设计本应的复杂度，
   不应让大量补丁堆出不必要的复杂度（设计简洁，实现复杂=方法有问题）
3. **设计符合度**：代码实现是否真的符合设计——逐项对照设计文档，
   发现偏差先推演确认，不急着测试（测试验证设计，不替设计纠错）

## 设计原则

沿用 pi-agents-meeting-discuss 的全部原则（确定性归 loop、状态从 git 共享
事实推导、单一事实源 = protocol.json、无静默铁律、测试对象 = 生产对象、
新概念禁令），并新增：

1. **信息层/流程层分离**：human 消息只影响信息层（agents 可读），
   流程判定对它"视而不见"（显式过滤非参与者，非物理隔离）。
2. **human 不参与轮转**：RR 轮转链完全由参与者 next 链驱动；
   `rr_next_speaker` 跳过非参与者消息。
3. **human 不解除冻结**：已冻结 agent 收到 human 插话不响应（发言锁优先）。
4. **配额对称增量**：human 每发一条消息，所有 agent 配额上限 +1，
   响应计入配额——不加快、不减慢配额消耗。
5. **human 保留名**：`human` 不可作为参与者名（报错）。

## 阶段划分

- **阶段 1**：核心脚本功能（human writer / rr_next_speaker / 配额增量 /
  setup 扩展）+ 测试调试。
- **阶段 2**：skill 层（SKILL.md / discuss.sh / npm 包装 / 主 pi 插话入口），
  阶段 1 调试通过后再实现。

## 设计文档

- `docs/pi-helper-design.md`：**本项目设计文档**（信息层/流程层分离、
  各阶段行为、配额语义、实现清单、测试策略）。

## Git 准则（用户约定，沿用源项目）

1. **每次改动先更新本地 git**：对本项目代码/文档的每次修改，先 `git add` + `git commit` 记录。
2. **阶段性完成即推送**：完成一个阶段性修改后，必须同时 `git push origin main` 推送到 GitHub。
3. **本地与远程保持同步**：提交后确认工作区干净、远程与本地 HEAD 一致。
4. **提交信息**：使用清晰、描述性的 message，说明本次改动内容。
5. **skill 设计文档同步**：阶段 2 对 skill 的任何修改，必须同步更新设计文档。
