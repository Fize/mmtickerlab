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

用已结束的美股交易日、A50 与美元人民币数据描述客观变化；明确哪些行情仍在交易，不把未收盘值写成收盘值。每项量化陈述在同一行标注证据编号，例如 `[E04]`。

- 隔夜事实：{{overnight_facts_and_citations}}
- 对 A 股开盘观察的含义：{{bounded_interpretation}}
- 不确定性：{{uncertainty}}

## 前一交易日结构

只使用前一交易日收盘快照、指数历史、近五日涨跌停活动和资金流快照。

| 观察项 | 已验证事实 | 解释 | 证据 |
|---|---|---|---|
| 指数与成交额 | {{index_and_turnover}} | {{interpretation}} | {{evidence_id}} |
| 市场宽度 | {{breadth}} | {{interpretation}} | {{evidence_id}} |
| 涨跌停与炸板 | {{limit_activity}} | {{interpretation}} | {{evidence_id}} |
| 行业/概念资金流 | {{fund_flows}} | {{interpretation}} | {{evidence_id}} |

## 今日观察框架

最多列三条可证伪的观察假设。条件必须来自数据包，不把假设写成事实；未配置自选股时删除自选股小节。

| 假设 | 盘中确认条件 | 失效条件 | 证据 |
|---|---|---|---|
| {{hypothesis_1}} | {{confirm_1}} | {{invalidate_1}} | {{evidence_id}} |
| {{hypothesis_2}} | {{confirm_2}} | {{invalidate_2}} | {{evidence_id}} |
| {{hypothesis_3}} | {{confirm_3}} | {{invalidate_3}} | {{evidence_id}} |

### 自选股观察（可选）

| 标的 | 历史位置与量价事实 | 今日观察条件 | 风险条件 | 证据 |
|---|---|---|---|---|
| {{code_and_name}} | {{verified_history}} | {{observe}} | {{risk}} | {{evidence_id}} |

## 风险与失效条件

- 数据风险：{{data_risk}}
- 市场结构风险：{{structure_risk}}
- 需要在盘中复核的关键假设：{{must_recheck}}

## 数据来源

逐项复制数据包的证据目录，不添加数据包之外的来源。

| 证据 | 数据集 | 目标日期 | 来源接口 | 采集时间 | 校验 |
|---|---|---|---|---|---|
| {{evidence_id}} | {{dataset}} | {{target_date}} | {{source}} | {{retrieved_at}} | 通过 |
