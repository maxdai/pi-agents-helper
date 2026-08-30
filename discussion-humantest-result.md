# 讨论结论：轻量任务队列的消息字段清单

## 结论摘要

轻量任务队列的消息采用 **7 字段最小清单**，可靠性字段（status / attempts / 锚点时间戳）是底线，业务与策略字段全部外推。该清单足以覆盖消息从入队到完结的完整生命周期：路由、执行、重试、超时回收、死信。

## 定稿字段清单（7 个）

| 字段 | 职责 |
|------|------|
| id | 唯一标识（ack / 去重 / 日志关联的基础） |
| type | 任务类型（消费者据此路由到对应 handler） |
| payload | 任务数据（不透明 JSON，业务字段全部收进 payload，保持外层稳定） |
| created_at | 入队时间（监控 / 统计） |
| updated_at | 租约锚点时间戳：最近一次状态流转的时间；running 态下即为领取时间，用于可见性超时判定，并支持 touch 续租 |
| status | 生命周期状态：pending → running → done / failed |
| attempts | 已尝试次数（配合阈值做重试上限） |

> 命名说明：自由讨论中曾比较 updated_at 与 claimed_at 两种命名，双方确认二者功能严格等价（running 时刻 claimed_at = 领取时间 = updated_at 该时刻的值），差异仅为语义表述风格。最终以唯一完整成文的总结记录 b/0005（updated_at 版）为会议产出锚定，claimed_at 不再变更。

## 配套规则

1. **领取**：`status=running, updated_at=now`（领取即租约开始）
2. **超时重投**：`now - updated_at > 租约阈值 → 重投, attempts++`
3. **终结**：`attempts ≥ max → status=failed`（即死信；不设独立 dead 状态）
4. **长任务**（可选扩展）：worker 执行中周期性 touch（刷新 updated_at）续租；最小实现可约定"租约阈值 > 最坏任务时长"

## 明确外推（不进核心 schema）

- **priority**：轻量场景 FIFO + type 分流足够，优先级是调度策略而非消息事实
- **timeout / delay**：属 worker 配置或用 created_at / updated_at 推导
- **dedup_key**：消费侧特性，可由 id 天然支持（同 id 重投可忽略）或放 payload
- **回调地址 / 结果存放位置**：作为约定放 payload 或由消费者自行上报

## 设计原则

**轻量 = 每个字段都要有"没有它就无法工作"的硬理由**：type 管路由、payload 管数据、id 管唯一性、created_at 管入队时间、updated_at 管租约锚点、status 管生命周期、attempts 管重试计数，各自承担不可省略的职责，没有冗余。可靠性字段（status/attempts/updated_at）是底线，业务与策略字段全部外推——这是轻量队列与全套 MQ 的分界线。

## 讨论过程要点

- 双方最初各自独立提出 6 字段清单（id/type/payload/status/attempts/created_at），完全一致
- 分歧 1：status 是否含 running 中间态 → 结论：必须含，它是"一次尝试"的定义者，也是崩溃恢复的最小代价（领取=租约）
- 分歧 2：租约超时需要时间戳且不能由 created_at 推导（created_at 是入队时间，会误伤长排队任务、拖慢崩溃回收）→ 结论：补锚点时间戳字段，第 7 字段
- 后续仅剩字段命名（updated_at vs claimed_at）的等价性讨论，确认等价后按唯一成文总结锚定收尾
