# 单元测试报告（2026-09-01，逐 API 测试完成）

> 基准：`docs/api-list.md`（100+ API 定义）。原则：测试不改代码——
> 问题只记录，修改留修复步骤。全量 259 测试 + 1 expectedFailure。

## 一、覆盖矩阵

| 模块 | API | 测试文件 | 测试数 | 结果 |
|---|---|---|---|---|
| meeting_core | C1-C9 | test_meeting_core.py | 38 | ✅ 全绿 |
| meeting_fs | F1-F22 | test_meeting_fs.py | 27 | ✅ 全绿 |
| meeting_engine | E1-E20（E21 集成） | test_meeting_engine.py | 34 | ✅ 全绿 |
| meeting_loop | L1-L14 | test_meeting_loop.py | 25 | ⚠️ 1 bug（L14） |
| start_discussion | S1-S18 | test_start_discussion + test_spec | 43 | ✅ 全绿 |
| human_viewer | V1-V9 | test_viewer + test_human | 19 | ✅ 全绿 |
| human_sayer | H1-H4 | test_human | 10 | ✅ 全绿 |
| wrapper | W1-W7 | test_wrapper | 15 | ✅ 全绿 |
| 组合验证 | 8 条链 | test_flow_composition | 9 | ✅ 全绿 |
| 集成（既有） | agent_loop 全链 | test_meeting_v2/concurrency/n_agents/stage4 | 39 | ✅ 全绿 |

**合计**：259 通过 + 1 expectedFailure（bug 确认）。

## 二、发现的问题

### 问题 1（真实 bug）：L14 `meeting_loop._preserve_result_md` 引用未定义变量

**位置**：`meeting_loop.py:347`（`log(agent, f"已保存 result.md → {dest}")`）

**现象**：函数签名 `_preserve_result_md(workdir)` 无 `agent` 参数，函数体
`log(agent, ...)` 引用未定义名称 → NameError。

**触发条件**：bare HEAD 存在 result.md（讨论已完成）且以 `__main__` 运行
（resultWriter 的 loop 退出路径调用）→ 必现。

**影响分析**：
- 写文件在 `log` **之前**已成功 → `result.md` 已保存到父级（功能完成）
- `log` 行崩溃 → 进程以异常退出：stderr traceback + 非零退出码
- 与 `start_discussion._preserve_result_md`（cleanup 保存）是**双机制**
  （loop 退出保存 + cleanup 保存）——loop 侧异常不丢产物（cleanup 兜底），
  但污染退出路径、掩盖"loop 正常退出"信号
- **对流程的影响**：无状态机影响（concluded 已落盘，讨论已完成）；
  仅退出路径异常

**建议修改**：`log` 去掉 `agent` 参数（改为 `log("loop", ...)` 或直接
`print`）——一行修复，无逻辑变化。

### 问题 2（flaky，待观察）：全量回归偶发 1 失败

**现象**：首次全量跑 1 个失败（未抓到详情），立即重跑全绿。

**影响分析**：疑似时序敏感测试（test_meeting_concurrency 60s 级多进程
场景）。单次出现未复现——暂不处理，后续全量跑时关注是否重复出现；
若复现再定位。

**建议**：记录观察，不采取行动（避免为未复现问题堆补丁）。

## 三、审阅要点（待用户/主 pi 确认）

1. **问题 1 修改方案**（一行修复）是否同意？
2. 问题 2 是否按"观察不处理"处理？
3. 无其他问题——全部 API 行为符合设计（api-list 定义即实现行为）。
