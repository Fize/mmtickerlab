---
name: first-board-overnight
description: 基于可审计 A 股数据执行首板隔夜模拟策略的决策技能。用于评估当日首板赚钱效应、筛选首板候选、生成带证据的 BUY、WATCH 或 NO_TRADE 决策、制定 T+1 退出计划，以及复盘模拟交易案例。必须与 market、sim-trade 和 plan-review 配合；不用于实盘交易、长期价值投资、无可靠快照的历史回测或把第三方交易经验冒充确定规则。
---

# First Board Overnight

把本技能作为策略决策层。让 `market` 提供数据，让 `sim-trade` 执行和记账，让 `plan-review` 提供通用盘前、盘中、盘后证据。不要在本技能中猜测行情、伪造成交或绕过任何数据门禁。

## 执行工作流

1. 明确任务阶段：`candidate_review`、`entry_decision`、`exit_plan` 或 `trade_review`。
2. 读取 [references/strategy.md](references/strategy.md)，确认策略目标、边界和市场环境门禁。
3. 读取 [references/data-acquisition.md](references/data-acquisition.md)，盘点现有证据并主动获取缺失的可恢复数据。缓存不存在不等于数据不可用。
4. 读取 [references/evidence-contract.md](references/evidence-contract.md)，区分直接证据、可重建证据和不可重建证据。
5. 获取完成后再定级：执行级证据完整为 `READY`；历史量价研究可完成但不能证明当时盘口或成交为 `RESEARCH_ONLY`；获取失败或连研究结论也无法支持才返回 `BLOCKED`。
6. 分析入场时读取 [references/entry-policy.md](references/entry-policy.md)；分析 T+1 退出时读取 [references/exit-policy.md](references/exit-policy.md)。
7. 涉及仓位或委托时读取 [references/risk-policy.md](references/risk-policy.md)。只有用户明确要求模拟下单且 `status: READY`、`decision: BUY` 时才调用 `sim-trade`；分析请求以及 `BLOCKED`、`RESEARCH_ONLY`、`WATCH`、`NO_TRADE` 结论不得创建委托。
8. 完成交易后读取 [references/review-schema.md](references/review-schema.md)，按决策时证据复盘，不使用结果反向改写原始理由。

## 决策纪律

- 始终先判断策略环境，再判断板块和个股；不要因单票盘口强而跳过环境门禁。
- 允许并优先保留 `NO_TRADE`。候选数量不是交易目标。
- 把板块地位、换手质量和资金合力标记为有证据的解释，不冒充可直接观测的事实。
- 不把固定时刻、市值、换手率、封单比例或止损比例视为所谓北京炒家的原始规则。未经样本验证的数值只能作为实验参数。
- 不宣称复刻任何个人的盘感或真实收益。本技能定义的是可验证的“首板隔夜实验策略”。
- 普通 A 股当日买入后次一交易日才可卖出；不得称为 T+0。
- 主动获取历史日线、分钟 K 线和技术指标来判断趋势、位置与量价状态；必要时使用 `scripts/render_chart.py` 绘制图表。
- 不基于收盘快照生成盘中可成交的入场决定，不使用当前数据回填历史盘口或成交事实。
- 不把涨停视为必然可买。以 `sim-trade` 返回的实际订单状态为准。

## 输出契约

每次策略判断必须输出：

1. `as_of`：交易日期、阶段和数据时间戳；
2. `status`：`READY`、`RESEARCH_ONLY` 或 `BLOCKED`；
3. `market_regime`：`FAVORABLE`、`MIXED`、`UNFAVORABLE` 或 `INSUFFICIENT_EVIDENCE`；
4. `decision`：`BUY`、`WATCH`、`NO_TRADE` 或 `EXIT_PLAN`；
5. `evidence`：逐条区分事实、解释和假设；
6. `counterevidence`：最强反证与失效条件；
7. `risk_plan`：仓位上限、最坏可接受损失和退出触发条件；
8. `execution`：`NOT_REQUESTED`、`NOT_ATTEMPTED` 及原因，或 `sim-trade` 的真实订单 ID、状态与未成交数量；`RESEARCH_ONLY` 永远不得执行；
9. `unknowns`：当前未采集或系统不支持的字段。

不得只给总分。若使用评分，必须同时展示构成证据、反证和未知项。
