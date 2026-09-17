# {{date}} 盘前计划

> bundle_id: `{{bundle_id}}`
>
> 数据包: `{{bundle_path}}`
>
> 生成时间: {{generated_at}}

## 数据状态

- 结论：全部必需数据通过结构、日期、时效与完整性校验。
- 目标交易日：{{date}}
- 前一交易日：{{previous_trading_day}}
- 证据范围：{{evidence_ids}}

## 隔夜与市场背景

- 隔夜事实：{{overnight_facts_and_citations}}
- 对 A 股开盘观察的含义：{{bounded_interpretation}}
- 不确定性：{{uncertainty}}

## 前一交易日结构

| 观察项 | 已验证事实 | 解释 | 证据 |
|---|---|---|---|
| 指数与成交额 | {{index_and_turnover}} | {{interpretation}} | {{evidence_id}} |
| 指数多周期位置与风格差 | {{index_history_and_style}} | {{interpretation}} | {{evidence_id}} |
| 市场宽度 | {{breadth}} | {{interpretation}} | {{evidence_id}} |
| 涨跌幅分布与极端排行 | {{distribution_and_rankings}} | {{interpretation}} | {{evidence_id}} |
| 涨跌停与炸板 | {{limit_activity}} | {{interpretation}} | {{evidence_id}} |
| 行业/概念 1/3/5 日资金流 | {{fund_flows}} | {{interpretation}} | {{evidence_id}} |

## 今日观察框架

| 假设 | 盘中确认条件 | 失效条件 | 证据 |
|---|---|---|---|
| {{hypothesis_1}} | {{confirm_1}} | {{invalidate_1}} | {{evidence_id}} |
| {{hypothesis_2}} | {{confirm_2}} | {{invalidate_2}} | {{evidence_id}} |
| {{hypothesis_3}} | {{confirm_3}} | {{invalidate_3}} | {{evidence_id}} |

### 自选股观察（可选）

| 标的 | K 线与技术指标事实 | 今日观察条件 | 风险条件 | 证据 |
|---|---|---|---|---|
| {{code_and_name}} | {{verified_history}} | {{observe}} | {{risk}} | {{evidence_id}} |

## 风险与失效条件

- 数据风险：{{data_risk}}
- 市场结构风险：{{structure_risk}}
- 需要在盘中复核的关键假设：{{must_recheck}}

## 数据来源

| 证据 | 数据集 | 目标日期 | 来源接口 | 采集时间 | 校验 |
|---|---|---|---|---|---|
| {{evidence_id}} | {{dataset}} | {{target_date}} | {{source}} | {{retrieved_at}} | 通过 |
