# Trade Review Schema

## 原则

复盘必须比较“决策时看到什么、当时预测什么、后来发生什么”。冻结原始决策，不以后见之明修改理由，不把偶然盈利归类为正确决策。

## Case 记录

每个候选或交易保存以下字段：

```yaml
case_id: unique identifier
strategy_version: first-board-overnight/v1
trade_date: YYYYMMDD
symbol: six-digit code
decision_timestamp: Asia/Shanghai timestamp
decision: BUY | WATCH | NO_TRADE
market_regime: FAVORABLE | MIXED | UNFAVORABLE
evidence_refs: []
facts: []
interpretations: []
hypotheses: []
counterevidence: []
unknowns: []
entry_plan: {}
execution:
  order_id: null
  status: NOT_REQUESTED
  fills: []
exit_plan: {}
observed_outcome: {}
review:
  process_quality: null
  thesis_result: null
  execution_quality: null
  attribution: []
  reusable_lesson: null
```

## 评价维度

- `process_quality`：数据是否完整、流程是否遵守、风险是否预定义；
- `thesis_result`：主要假设被确认、部分确认、否定或证据不足；
- `execution_quality`：委托是否按计划、滑点、部分成交和退出偏差；
- `outcome`：净收益、最大有利/不利变动和持有时间；
- `attribution`：环境、板块、选股、时机、成交和退出分别贡献什么。

盈利但违反门禁应判定为坏流程；亏损但严格执行且假设合理可以判定为合格流程。

## 聚合评估

样本达到预先设定数量后，再按策略版本统计成交率、胜率、期望收益、盈亏比、最大回撤、不同市场环境表现和不同候选类型表现。不要混合不同规则版本，也不要把未成交候选算作已成交收益。
