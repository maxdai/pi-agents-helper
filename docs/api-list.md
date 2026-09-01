# 脚本 + API 清单（单元测试基准）

> 2026-09-01 启动的单元测试重设计工程。本清单是对每个 API 功能的**精确
> 定义**——作为逐 API 单元测试的基准。每个 API 需测：各种可能出现的情况
> （正常/边界）+ 各种不应该出现的情况（异常/非法/状态不符）。
> **状态列**（进度单一事实源）：待测 / 已测(结果) / 审阅(结论) / 已修 / 复测(通过)。

## 测试覆盖原则

- 正常路径：文档定义的输入 → 期望输出
- 边界：空输入 / 单元素 / 最大 / 缺失字段 / 畸形格式
- 异常（不应该出现）：非法 type / 不完整 frontmatter / git 失败 / 目录缺失 /
  并发冲突 / 状态不符（如非 RR 阶段查 next）

---

## 一、meeting_core.py（纯逻辑，无 I/O——判定函数只吃数据结构）

| # | API | 功能定义 | 状态 |
|---|---|---|---|
| C1 | `last_message_type(messages)` | 按序号升序的消息列表 → 最后一条的 type；空列表 → None | 已测(通过) |
| C2 | `is_all_last(by_agent, predicate)` | 所有参与者最后一条消息满足 predicate；有人从未发言（None）→ False | 已测(通过) |
| C3 | `is_all_last_in(by_agent, types)` | 所有参与者最后一条 ∈ types（宽松确认，freezing 或 af 均可） | 已测(通过) |
| C4 | `read_point_seen_at(messages)` | 读取点 = 最后一条消息的 seen_at；无消息 → ""（从根读起） | 已测(通过) |
| C5 | `validate_and_fix(fm, agent, mode, head, allow_protocol_types=False, loop_message=False)` | 校验并确定性修复 frontmatter：from 缺失/错误→agent；seen_at：LLM 消息缺失/≠head→head，loop 消息仅缺省兜底；mode 无条件覆盖；type 白名单（默认 {message,freezing,pass}，协议路径全量）非法→errors；to 无条件强制 all。返回 (fixed, errors) | 已测(通过) |
| C6 | `has_new_messages_for_me(new_messages, me)` | 有别人消息且 to∈{me,all,缺省} → True；自己的消息不触发 | 已测(通过) |
| C7 | `should_write_af(all_last_types)` | 全员冻结（freezing/af，宽松版）→ True；有人 None → False；空 → False | 已测(通过) |
| C8 | `can_start_rr(all_last_types)` | 全员最后一条都是 all-freezing → True（单条件严格版） | 已测(通过) |
| C9 | `aggregate_mode(all_last)` | 全局模式聚合：任一 concluded→concluded；任一 mode==round-robin→round-robin；全员 freezing/af→all-freezing；否则 meeting；空→meeting | 已测(通过) |

**core 关键边界/异常**：
- C5：type=None / type 非法（如 "concluded" 默认路径）→ errors 且 mode 仍修复；
  to 任意值（含非法）→ "all"；from 缺失/空/错误 → agent
- C6：to 缺失（缺省 all）触发；from==me 不触发；空列表 → False
- C7/C8：all_last 空 dict → False；部分 None → False；mixed 类型 → False
- C9：全 None（无人发言）→ meeting；pass 存在但 mode 缺失 → meeting（pass 不升 RR）

---

## 二、meeting_fs.py（文件/git 操作层）

| # | API | 功能定义 | 状态 |
|---|---|---|---|
| F1 | `run_git(workdir, *args, check=True, timeout=30)` | 执行 git 命令；check 且非零退出 → RuntimeError（含 out/err 截断）；否则返回 CompletedProcess | 已测(通过) |
| F2 | `git_head(workdir)` | 当前 HEAD（rev-parse HEAD，strip） | 已测(通过) |
| F3 | `git_pull(workdir)` | pull --rebase --autostash（check=False） | 已测(通过) |
| F4 | `git_commit(workdir, files, subject)` | add 指定文件 + commit（每 commit 一条消息约束） | 已测(通过) |
| F5 | `git_push(workdir)` | push 带并发容错：非快进 → pull --rebase → 重推，5 次耗尽 → RuntimeError（消息不得滞留本地） | 已测(通过) |
| F6 | `git_ls_files(workdir, agent_dir)` | 列出 agent 目录已提交消息文件（排序）；无 → [] | 已测(通过) |
| F7 | `git_show(workdir, commit, path)` | 读 commit 中文件；失败 → None | 已测(通过) |
| F8 | `_frontmatter_end(content)` | 块边界：开 `---`（严格 startswith）+ 闭 `---`（strip 比较）→ 闭合行号；不完整 → None | 已测(通过) |
| F9 | `parse_frontmatter(content)` | 块完整才解析（先边界后解析）；字段 `key: value` 正则，剥引号；不完整 → None | 已测(通过) |
| F10 | `extract_body(content)` | frontmatter 块后正文（strip）；块不完整 → None | 已测(通过) |
| F11 | `read_message(workdir, path)` | 读消息文件 → (fm, content)；文件不存在 → (None, None) | 已测(通过) |
| F12 | `_fm_to_lines(frontmatter)` | fm dict → 行列表（`---` + 键值行 + `---`）；值单行化 + 剥引号 | 已测(通过) |
| F13 | `write_message(workdir, path, fm, body)` | 写文件（frontmatter + 空行 + body）；父目录自动建 | 已测(通过) |
| F14 | `serialize_message(fm, original)` | 替换原文件 frontmatter 保留 body；首行 `---`（**允许前导空格**，与 F8 语义刻意分离）缺失 → None；无闭合 → None | 已测(通过) |
| F15 | `list_my_messages(workdir, agent_dir)` | agent 全部消息（含 frontmatter）按序号升序；parse 失败的跳过 | 已测(通过) |
| F16 | `next_msg_id(workdir, agent_dir)` | 下个序号 = max+1（4 位补零，跳号安全）；无消息 → 0001 | 已测(通过) |
| F17 | `commit_message(agent, msg_id)` | `discuss: agent/msg_id` 格式 | 已测(通过) |
| F18 | `read_point(workdir, agent_dir)` | 读取点 = 最后一条参与消息的 seen_at（跳 freezing）；"" = 从根 | 已测(通过) |
| F19 | `list_new_messages(workdir, since_ref)` | since 后新消息文件路径（ls-tree 全量 / diff since..HEAD）；只保留消息文件；空 since → 全部 | 已测(通过) |
| F20 | `new_messages_with_meta(workdir, since_ref, me=None)` | 新消息带元数据 {path, from, to, seen_at, stale}；stale = seen_at 之后有**其他**消息更新（diff seen_at..HEAD）；me 过滤自己的；parse 失败跳过 | 已测(通过) |
| F21 | `is_message_file(path)` | `^[a-z]+/\d{4}\.md$` 判定 | 已测(通过) |
| F22 | `parse_log_nameonly(output)` | `git log --name-only` 输出 → [(commit, [files])]；按拓扑序；空行跳过；非 40 位 hex 行视为文件 | 已测(通过) |

**fs 关键边界/异常**：
- F5：push 一直失败 → RuntimeError（5 次后）；失败中途成功 → 返回
- F8/F9/F10：无开 `---` / 有开无闭 / `---` 前导空格（F9 严格，F14 宽松）
- F9：非法行（无冒号）跳过；引号包裹值剥引号；值含中文/冒号
- F16：非数字文件（README.md）不计数；跳号（0005 存在无 0001-0004）→ 0006
- F19/F20：since_ref 非法 ref → git diff 失败（check=False 静默空）——验证行为
- F22：commit 行 = 40 hex；文件行可含空格；空输出 → []

---

## 三、meeting_engine.py（唯一状态机）

| # | API | 功能定义 | 状态 |
|---|---|---|---|
| E1 | `participants(workdir)` | protocol.json → participants 列表 | 已测(通过) |
| E2 | `result_writer(workdir)` | protocol.json → resultWriter（缺省 = 最后参与者） | 已测(通过) |
| E3 | `_each_agent_messages(bare, agents)` | bare 树每 agent 完整消息列表（fm 按序号升序）；cat-file 批量读；parse 失败跳过；无消息 → {a: []} | 已测(通过) |
| E4 | `_cat_batch(bare, paths)` | git cat-file --batch 批量读 → {path: content}；二进制字节读（中文安全）；missing → 跳过；异常安全（stdin 关闭 + wait） | 已测(通过) |
| E5 | `_each_agent_last(bare, agents)` | 每 agent 最后一条 {type, mode, next}；无消息 → None | 已测(通过) |
| E6 | `aggregate_mode(bare, agents)` | 引擎版聚合（stall 分支用，调 core C9） | 已测(通过) |
| E7 | `rr_next_speaker(bare, agents)` | RR 下一位：HEAD 是参与者消息 → 原语义（git log -1 + 最后消息文件 next）；HEAD 是 human → 逐 commit 回退找最近参与者消息的 next；找不到 → None | 已测(通过) |
| E8 | `rr_active_count(messages, agents)` | starter 的 mode==round-robin 消息数（RR 轮数） | 已测(通过) |
| E9 | `_meeting_speak_count(messages, agent)` | agent 的 mode==meeting 且 type==message 消息数（配额） | 已测(通过) |
| E10 | `human_msg_count(bare)` | bare 中 human/ 下消息文件数（配额增量） | 已测(通过) |
| E11 | `_produced(workdir, agent, before)` | 我的消息数 > before（产出判定） | 已测(通过) |
| E12 | `write_af_if_no_rr(bare, workdir, agent, agents)` | 写 af 前 pull + 重检：bare 已有 RR（任一最后一条 mode==round-robin）→ 放弃；否则写 af | 已测(通过) |
| E13 | `write_protocol_signal(workdir, agent, type_, mode, next_=None)` | 写流程控制消息：写前 pull + 重取 head；seen_at = 读取点或 head 兜底；pass 带 next 链；validate(协议路径) + commit + push | 已测(通过) |
| E14 | `respond_with_fallback(workdir, agent, responder, head, meta, is_first, rr_turn, before, agents)` | 一次响应轮：responder → commit_new_files → 查产出；无产出重试 MAX_RETRY；仍失败 → loop 代写（RR→pass 带 next / meeting→freezing）；代写返回 False | 已测(通过) |
| E15 | `commit_new_files(workdir, agent, head, mode)` | 校验/补全 agent 写的内容文件 + commit + push：无 frontmatter → 删除等待重写；type 非法 → 删除拦截；RR 阶段 pass/message 补 next（无条件覆盖顺序下一位）；serialize 重写 | 已测(通过) |
| E16 | `_is_committed(workdir, path)` | 文件是否 tracked（已提交）；modified 的 tracked 文件仍视为已提交 | 已测(通过) |
| E17 | `_stall_elapsed(bare, agents, last_head, last_head_time, head)` | 无进展累计：无消息文件 → 不累计（0, head, now）；HEAD 未变 → 累计；HEAD 变 → 重置 | 已测(通过) |
| E18 | `_result_md_valid(result_path)` | result.md 存在 + 非空 + >50 字符 | 已测(通过) |
| E19 | `finalize_discussion(workdir, agent, responder, head, reason)` | 收尾：唤醒 rw 写 result.md → 校验 → 重试 MAX_RETRY → 仍无效 loop 兜底代写 → commit result.md → 写 concluded | 已测(通过) |
| E20 | `_commit_result_md(workdir, agent, subject)` | 幂等提交 result.md：status --porcelain 有改动才 commit（无改动跳过） | 已测(通过) |
| E21 | `agent_loop(workdir, agent, responder, max_meeting, max_rr, poll_interval, stall_timeout)` | 主状态机：①repo.git 消失→退出 ②concluded→退出 ③stall 超时→rw 收尾/非 rw 接管仲裁 ④全员冻结→写 af ⑤all-freezing→starter 启动 RR（有新消息唤醒/pass 确定性写）⑥RR：全员 pass→rw 收尾、max_rr 兜底、next 驱动、无新消息确定性 pass ⑦meeting：首启/配额耗尽冻结/触发/唯一未冻结冻结/发言锁/配额内响应；异常不终止循环 | 已测(集成:test_meeting_v2+fake_agent 全链+组合链) |

**engine 关键边界/异常**：
- E7：HEAD 是 human 且往前无参与者消息 → None；HEAD 参与者但 fm 不可用 → None；
  同 commit 多消息文件 → 取最后一个（等价性）
- E13：type_=pass 时 mode 强制 round-robin + next；loop 消息 seen_at 沿用
- E14：responder 抛异常（RecoverableWakeError）→ 穿透（不代写）；responder 产出但 commit 无文件（校验拦截）→ 视为无产出
- E15：文件目录不存在 → False；无新文件 → False；RR 阶段违规 message 也补 next
- E17：setup 后无消息 → 0；连续无进展 → 增长；HEAD 变 → 0
- E19：result.md 重试后无效 → 兜底代写 + 仍 commit + concluded
- E21：stall 接管仲裁（非 rw 先 pull 重检 concluded/result.md 已提交 → 让位）

---

## 四、meeting_loop.py（Pi 适配层）

| # | API | 功能定义 | 状态 |
|---|---|---|---|
| L1 | `RecoverableWakeError` | 可恢复唤醒失败异常（内存不足）——引擎 sleep 下轮重试，不代写 | 已测(通过) |
| L2 | `_handle_sigterm(sig, frame)` | SIGTERM：terminate 唤醒中的 pi 子进程（_kill_proc）→ SystemExit(0)；无进程直接退出 | 已测(通过) |
| L3 | `_kill_proc(proc)` | 终止子进程：SIGTERM → 5s 未退 SIGKILL（兜底必杀）；已退出直接返回 | 已测(通过) |
| L4 | `mem_available_mb()` | /proc/meminfo MemAvailable → MB；不可读 → 99999 | 已测(通过) |
| L5 | `session_id(workdir, agent)` | `discuss-<base名>-<agent>`（非法字符转 -） | 已测(通过) |
| L6 | `load_session_id(workdir, agent)` | 读 status-<agent>.json 的 sessionID；无 → None | 已测(通过) |
| L7 | `save_session_id(workdir, agent, sid)` | 写 status-<agent>.json {"sessionID": sid} | 已测(通过) |
| L8 | `parse_session(stdout)` | 扫描 JSON 行取 type=session 的 id；兼容旧式 sessionID；无 → None | 已测(通过) |
| L9 | `read_agent_config(workdir, agent)` | 读 pi-agent.json（model/thinking/prompt_file）→ dict | 已测(通过) |
| L10 | `build_wake_prompt(agent, meta, is_first, state, retry, msg_path)` | 唤醒提示：重试声明/首启声明/消息路径/状态/必须 frontmatter 说明/新消息清单（无陈旧标注） | 已测(通过) |
| L11 | `_lock_git(workdir)` / `_unlock_git(workdir)` | .git ↔ .git.locked 原子改名（唤醒期防 LLM git 破坏）；recover_git_lock 兜底恢复 | 已测(通过) |
| L12 | `wake_llm(workdir, agent, prompt, pure)` | spawn pi（--mode json --session-id --approve --print 等）；分片 communicate（15s）检测 repo.git 消失 → _kill_proc + SystemExit(0)；总超时 → _kill_proc + TimeoutExpired；正常 → parse session + save + returncode 分支（No session found 清 status）；返回 (new_sid, returncode) | 已测(通过) |
| L13 | `make_responder(pure)` | 构造 responder：finalizing → 写 result.md 提示；RR → pass 提示；meeting → 消息路径提示；内存不足 → RecoverableWakeError；调 wake_llm | 已测(通过) |
| L14 | `_preserve_result_md(workdir)` | bare HEAD:result.md → 父级 <base名>-result.md；无 → 跳过 | 已测→修复(2026-09-01: log 去 agent 参数)+复测(通过) |

**loop 关键边界/异常**：
- L3：terminate 后 poll 已退出 → 不 kill；communicate 超时 → kill + 再 communicate
- L8：非 JSON 行跳过；多 session 头取第一个
- L12：pi 正常返回 rc=0 → (sid, 0) + status 写入；rc≠0 非 session 错误 → status 保留；
  No session found → status 删除；目录清理 → SystemExit(0)（非异常）；总超时 → TimeoutExpired
- L13：finalizing 时 retry 提示不同；MIN_MEM 检查在 wake 前

---

## 五、start_discussion.py（环境生成/生命周期）

| # | API | 功能定义 | 状态 |
|---|---|---|---|
| S1 | `run(cmd, cwd=None, check=True)` | subprocess.run；check 且非零 → RuntimeError | 已测(通过) |
| S2 | `_spec_read(spec_dir, rel)` | 读 spec 文件跳过首行（说明行）；文件不存在 → None | 已测(通过) |
| S3 | `_default_model()` | pi settings.json → provider/model；defaultModel 含 / 直接用；无配置/失败 → None | 已测(通过) |
| S4 | `_spec_models(spec_dir, participants)` | 解析 models.md → {agent: (model, variant)}；容错（空行/无冒号/不在 participants 跳过）；default → None / max | 已测(通过) |
| S5 | `_strip_empty_sections(question)` | 去占位符可选节（- X: 立场 / - 问题，连标题）；已填节保留 | 已测(通过) |
| S6 | `gen_spec_skeleton(spec_dir, participants)` | 生成 spec 骨架：README + question.md + background.md + models.md + agents/X.md + .order（首行说明） | 已测(通过) |
| S7 | `gen_agens_md(args, agent, participants, spec_background)` | 协议 AGENTS.md（模板填充：agent 名/参与者/背景）；spec_background 优先 | 已测(通过) |
| S8 | `gen_agent_def(agent, participants, models, stances, extra, variant)` | agent prompt 文件（模板填充 + model_body + stance_ref + extra 追加） | 已测(通过) |
| S9 | `gen_question(topic, stances, background, questions)` | question.md：主题 + 可选立场 + 可选待答问题 | 已测(通过) |
| S10 | `gen_protocol(topic, participants, max_meeting, max_rr, pure, result_writer, stall_timeout)` | protocol.json dict（mode/protocol_version/topic/participants/resultWriter/配额/stall/commitPolicy；pure 标记） | 已测(通过) |
| S11 | `_resolve_path(p)` | 含 /~. → 绝对路径；否则 cwd 拼接 | 已测(通过) |
| S12 | `_resolve_spec(spec, agents, topic, background, stances, questions, models)` | --spec 解析：与内容参数互斥校验；目录/agents/ 存在；participants 从 .order + .md 推断；question.md 必填且正文非空；返回 (dir, participants, error) | 已测(通过) |
| S13 | `_clone_work(base, p)` | clone work-<p> + git 身份 + 建 .pi/agent/ 与 <p>/ 目录 | 已测(通过) |
| S14 | `setup_environment(args, participants, base, spec_dir)` | 生成讨论环境：spec 预读（question 去占位符节/background/agents）+ models 解析（spec/CLI/default 兜底）+ bare init + work clone + 共享配置 + 本地配置 + setup commit + 重建 work + work-human + 复制模块 | 已测(通过) |
| S15 | `_preserve_result_md(base)` | bare HEAD:result.md → 父级 <base名>-result.md；无 → 跳过 | 已测(通过) |
| S16 | `cleanup_discussion(base)` | 保存 result.md（若存在）→ 删目录；目录不存在 → 提示返回 | 已测(通过) |
| S17 | `check_status(base)` | 状态：bare 不存在 → not-exists；result.md 在历史 + concluded 存在 → done；有 result 无 concluded → running；有 loop 进程 → running；否则 stopped | 已测(通过) |
| S18 | `main()` | CLI 入口（--dir/--agents/--topic/--stances/--background/--questions/--models/--max-meeting/--max-rr/--spec/--spec-gen/--result-writer/--pure/--start/--status/--wait/--cleanup/--stall-timeout） | 已测(通过) |

**start 关键边界/异常**：
- S2：首行跳过；只有首行 → ""；不存在 → None
- S4：行格式错误（缺冒号/多逗号）容错；variant 缺省 max
- S12：agents 显式传（含默认值）与 --spec 互斥；spec 目录不存在；agents/ 缺失；
  无 agent 文件；question.md 缺失/空正文 → error
- S14：重建段 local_files 保留；work-human 独立创建（循环外）；human 保留名校验
- S17：pgrep 边界（discussion-1 不匹配 discussion-1x）

---

## 六、human_viewer.py（只读展示）

| # | API | 功能定义 | 状态 |
|---|---|---|---|
| V1 | `_protocol(bare)` | HEAD:protocol.json → dict；读不到/非法 JSON → {} | 已测(通过) |
| V2 | `participants_from_bare(bare)` | protocol.json participants；无 → None | 已测(通过) |
| V3 | `result_path(base, bare)` | work-<resultWriter>/result.md 路径；无 rw → "" | 已测(通过) |
| V4 | `new_messages(bare, since)` | since 后新消息文件（log --reverse 拓扑序旧→新）→ [(commit, path)]；只含消息文件（含 human/） | 已测(通过) |
| V5 | `format_message(path, content)` | 消息 → 展示行（header + summary + body + ---）；frontmatter 不可用 → None | 已测(通过) |
| V6 | `incremental(bare, agents, since)` | 单次增量 → (mode, lines, head, done)；done = mode==concluded | 已测(通过) |
| V7 | `_cursor_path/_read_cursor/_write_cursor(base)` | .viewer-cursor 游标读写；无 → None | 已测(通过) |
| V8 | `follow(base, bare, agents, poll_interval)` | 循环增量展示直到 done；状态变化打印【状态】；done 打印 result 路径并返回 | 已测(通过) |
| V9 | `main()` | CLI：bare 不存在/无 participants → 错误返回 1；BrokenPipeError → 静默退出 0 | 已测(通过) |

---

## 七、human_sayer.py（human 插话写入）

| # | API | 功能定义 | 状态 |
|---|---|---|---|
| H1 | `_summary(body)` | 正文首个非空行截取 ≤60 字符；无 → "" | 已测(通过) |
| H2 | `say(workdir, body)` | 写 human 消息：flock 串行 → pull → head/mode/序号 → frontmatter（from=human/type=message/mode=当前聚合/seen_at=head/to=all/summary）→ write → commit → push 容错；返回 (path, summary) | 已测(通过) |
| H3 | `interactive(workdir)` | 交互：逐行累积、空行提交（有累积）、Ctrl-D 退出 | 已测(通过) |
| H4 | `main()` | CLI：bare/work-human 不存在 → 错误返回 1；文本参数或 stdin；空内容 → 错误 | 已测(通过) |

---

## 八、scripts/discuss.sh（wrapper，bash）

| # | 命令 | 功能定义 | 状态 |
|---|---|---|---|
| W1 | `--prepare "<问题>" [--background "<背景>"] [--agents N\|列表]` | 生成 spec（含 models.md 继承主 pi model/thinking）；human 保留名校验；输出 spec 路径 | 已测(通过) |
| W2 | `--start <spec>` | setup + 启动 N 个 loop 进程；输出讨论目录 + 完整 !! 观看命令 | 已测(通过) |
| W3 | `--view <dir> [--since <ref>]` | viewer 封装（增量展示） | 已测(通过) |
| W4 | `--say <dir> <文本>` | sayer 封装（插话） | 已测(通过) |
| W5 | `--status <dir>` | status 查询 | 已测(通过) |
| W6 | `--cleanup <dir>` | 清理（保存 result.md + 删目录） | 已测(通过) |
| W7 | `check_aft_bash` | aft bash:false 配置检查（缺失 → 4 行警告，不阻断） | 已测(通过) |

---

## 组合逻辑验证（API 清单应符合设计流程）

> 动态拼接验证 2026-09-01（tests/test_flow_composition.py，9 测试全绿）：
> 用真实 API 逐链拼装（非 agent_loop 整体），断链点 = 清单或实现漏洞。

1. **setup 链**：S14（gen_protocol + gen_agens_md + gen_agent_def + question/background/models 注入）→ E1/E2 读到一致的 participants/resultWriter ✅（chain1）
2. **消息写入链**：responder 写内容文件 → E15 commit_new_files（C5 校验 + RR next）→ F4/F5 commit+push → bare 可见 ✅（chain2）
3. **状态判定链**：E3/E5（bare 组装）→ C9 aggregate_mode → E21 分支分派 ✅（chain3）
4. **配额链**：E9（meeting speak）+ E10（human count）→ ⑤.2 冻结判定 ✅（chain4）
5. **RR 链**：C8 can_start_rr → E13 pass（带 next）→ E7 rr_next_speaker → 轮转 ✅（chain5）
6. **收尾链**：E19 finalize（E18 校验 + E20 幂等 commit + concluded）→ E21 退出 → S17 done 判定（result.md + concluded）✅（chain6）
7. **human 通道**：H2 say（E10 配额增量数据源）→ V4 viewer 展示 → agents 响应 ✅（chain7）
8. **清理链**：S16 cleanup（S15 保存 result）→ loop 自退（repo.git 消失检测 + L12 分片）→ 无残留 ✅（chain8）

**拼接结论**：全部链输入输出衔接无断点；API 清单与设计流程一致。
后续逐 API 单测阶段以本清单为基准逐条细化断言。
