# {{date}} 盘中复盘

> bundle_id: `{{bundle_id}}`
>
> 数据包: `{{bundle_path}}`
>
> 对照盘前报告: `{{pre_report_path}}`
>
> 生成时间: {{generated_at}}

## 数据状态

- 结论：盘前报告存在，午间快照及全部必需数据均已通过校验。
- 快照窗口：11:30-13:00（Asia/Shanghai）
- 证据范围：{{evidence_ids}}

## 上午市场事实

| 观察项 | 午间事实 | 相对前收变化 | 证据 |
|---|---|---|---|
| 主要指数 | {{indices}} | {{change}} | {{evidence_id}} |
| 成交额与市场宽度 | {{turnover_and_breadth}} | {{change}} | {{evidence_id}} |
| 涨跌停活动 | {{limit_activity}} | {{change}} | {{evidence_id}} |
| 行业/概念资金流 | {{fund_flows}} | {{change}} | {{evidence_id}} |

## 与盘前假设的对照

逐条引用盘前假设原文并判定“确认 / 部分确认 / 失效 / 证据不足”。不能新增一个未经盘前提出的假设来宣称判断正确。

| 盘前假设 | 状态 | 午间证据 | 判断 |
|---|---|---|---|
| {{hypothesis_1}} | {{status}} | {{fact_and_evidence}} | {{reason}} |
| {{hypothesis_2}} | {{status}} | {{fact_and_evidence}} | {{reason}} |
| {{hypothesis_3}} | {{status}} | {{fact_and_evidence}} | {{reason}} |

## 结构变化

- 强于盘前预期：{{stronger_with_evidence}}
- 弱于盘前预期：{{weaker_with_evidence}}
- 新出现但尚未确认：{{new_unconfirmed}}
- 上午主导结构：{{structure_conclusion}}

## 下午观察框架

| 观察点 | 继续成立条件 | 失效条件 | 下午收盘需验证的数据 |
|---|---|---|---|
| {{observation_1}} | {{confirm}} | {{invalidate}} | {{close_metric}} |
| {{observation_2}} | {{confirm}} | {{invalidate}} | {{close_metric}} |
| {{observation_3}} | {{confirm}} | {{invalidate}} | {{close_metric}} |

## 数据来源

| 证据 | 数据集 | 目标日期 | 来源接口 | 采集时间 | 校验 |
|---|---|---|---|---|---|
| {{evidence_id}} | {{dataset}} | {{target_date}} | {{source}} | {{retrieved_at}} | 通过 |
