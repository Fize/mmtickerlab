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

## 市场概览

| 指标 | 午间值 | 相对前收/历史同期 | 证据 |
|---|---:|---:|---|
| 主要指数与风格 | {{index_overview}} | {{style_change}} | {{evidence_id}} |
| 成交额 | {{turnover}} | {{turnover_change}} | {{evidence_id}} |
| 上涨/平盘/下跌家数 | {{breadth_counts}} | {{breadth_change}} | {{evidence_id}} |
| 领涨/领跌板块 | {{leading_sectors}} | {{sector_change}} | {{evidence_id}} |
| 资金流向 | {{flow_overview}} | {{flow_change}} | {{evidence_id}} |

## 恐慌贪婪指数

| 总分 | 等级 | 较前一可比时点 | 计算版本 | 证据 |
|---:|---|---:|---|---|
| {{fear_greed_score}} | {{fear_greed_level}} | {{fear_greed_change}} | {{fear_greed_version}} | {{evidence_id}} |

| 分项 | 得分 | 权重 | 贡献 | 证据 |
|---|---:|---:|---:|---|
| 成交量 | {{fg_volume_score}} | {{fg_volume_weight}} | {{fg_volume_contribution}} | {{evidence_id}} |
| 市场广度 | {{fg_breadth_score}} | {{fg_breadth_weight}} | {{fg_breadth_contribution}} | {{evidence_id}} |
| RSI | {{fg_rsi_score}} | {{fg_rsi_weight}} | {{fg_rsi_contribution}} | {{evidence_id}} |
| 价格动量 | {{fg_momentum_score}} | {{fg_momentum_weight}} | {{fg_momentum_contribution}} | {{evidence_id}} |
| 波动率 | {{fg_volatility_score}} | {{fg_volatility_weight}} | {{fg_volatility_contribution}} | {{evidence_id}} |

## 商品行情

| 类别 | 品种/合约 | 最新价 | 涨跌幅 | 5日变化 | 时点/状态 | 证据 |
|---|---|---:|---:|---:|---|---|
| {{commodity_category}} | {{commodity_contract}} | {{commodity_price}} | {{commodity_change}} | {{commodity_5d}} | {{commodity_asof}} | {{evidence_id}} |

## 上午市场事实

| 观察项 | 午间事实 | 相对前收变化 | 证据 |
|---|---|---|---|
| 主要指数 | {{indices}} | {{change}} | {{evidence_id}} |
| 成交额与市场宽度 | {{turnover_and_breadth}} | {{change}} | {{evidence_id}} |
| 涨跌分布与异动排行 | {{distribution_and_rankings}} | {{change}} | {{evidence_id}} |
| 涨跌停活动 | {{limit_activity}} | {{change}} | {{evidence_id}} |
| 行业/概念 1/3/5 日资金流 | {{fund_flows}} | {{change}} | {{evidence_id}} |
| 大单数据（可选） | {{large_trades_or_unavailable}} | 仅作异常线索 | {{evidence_id}} |

## 与盘前假设的对照

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
