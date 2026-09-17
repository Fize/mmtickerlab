# {{date}} 盘后复盘

> bundle_id: `{{bundle_id}}`
>
> 数据包: `{{bundle_path}}`
>
> 对照报告: `{{pre_report_path}}`、`{{noon_report_path}}`
>
> 生成时间: {{generated_at}}

## 数据状态

- 结论：盘前和盘中报告均存在；独立采集的收盘快照与龙虎榜数据均已通过校验。
- 证据范围：{{evidence_ids}}

## 市场概览

| 指标 | 收盘值 | 午后变化 | 较前日变化 | 证据 |
|---|---:|---:|---:|---|
| 主要指数与风格 | {{index_overview}} | {{style_change}} | {{day_change}} | {{evidence_id}} |
| 全天成交额 | {{turnover}} | {{afternoon_turnover_change}} | {{turnover_day_change}} | {{evidence_id}} |
| 上涨/平盘/下跌家数 | {{breadth_counts}} | {{afternoon_breadth_change}} | {{breadth_day_change}} | {{evidence_id}} |
| 领涨/领跌板块 | {{leading_sectors}} | {{sector_change}} | {{sector_day_change}} | {{evidence_id}} |
| 资金流向 | {{flow_overview}} | {{flow_change}} | {{flow_day_change}} | {{evidence_id}} |

## 恐慌贪婪指数

| 总分 | 等级 | 较午间 | 较前日收盘 | 计算版本 | 证据 |
|---:|---|---:|---:|---|---|
| {{fear_greed_score}} | {{fear_greed_level}} | {{fear_greed_noon_change}} | {{fear_greed_day_change}} | {{fear_greed_version}} | {{evidence_id}} |

| 分项 | 得分 | 权重 | 贡献 | 证据 |
|---|---:|---:|---:|---|
| 成交量 | {{fg_volume_score}} | {{fg_volume_weight}} | {{fg_volume_contribution}} | {{evidence_id}} |
| 市场广度 | {{fg_breadth_score}} | {{fg_breadth_weight}} | {{fg_breadth_contribution}} | {{evidence_id}} |
| RSI | {{fg_rsi_score}} | {{fg_rsi_weight}} | {{fg_rsi_contribution}} | {{evidence_id}} |
| 价格动量 | {{fg_momentum_score}} | {{fg_momentum_weight}} | {{fg_momentum_contribution}} | {{evidence_id}} |
| 波动率 | {{fg_volatility_score}} | {{fg_volatility_weight}} | {{fg_volatility_contribution}} | {{evidence_id}} |

## 商品行情

| 类别 | 品种/合约 | 收盘/最新价 | 涨跌幅 | 5日变化 | 时点/状态 | 证据 |
|---|---|---:|---:|---:|---|---|
| {{commodity_category}} | {{commodity_contract}} | {{commodity_price}} | {{commodity_change}} | {{commodity_5d}} | {{commodity_asof}} | {{evidence_id}} |

## 收盘事实

| 观察项 | 收盘事实 | 午后变化 | 证据 |
|---|---|---|---|
| 主要指数 | {{indices}} | {{afternoon_change}} | {{evidence_id}} |
| 成交额与市场宽度 | {{turnover_and_breadth}} | {{afternoon_change}} | {{evidence_id}} |
| 涨跌分布与异动排行 | {{distribution_and_rankings}} | {{afternoon_change}} | {{evidence_id}} |
| 涨跌停与炸板 | {{limit_activity}} | {{afternoon_change}} | {{evidence_id}} |
| 行业/概念 1/3/5 日资金流 | {{fund_flows}} | {{afternoon_change}} | {{evidence_id}} |

## 盘前与盘中判断复核

| 原判断 | 来源 | 最终状态 | 收盘证据 | 偏差原因 |
|---|---|---|---|---|
| {{judgment}} | 盘前/盘中 | 确认/部分确认/失效/证据不足 | {{fact_and_evidence}} | {{cause}} |

## 题材生命周期

| 分类 | 定义 |
|---|---|
| 观察 | 首次出现，证据不足以确认持续性 |
| 启动 | 广度和强度同步改善，资金开始一致 |
| 扩散 | 参与面继续扩大，核心与跟随均增强 |
| 高潮 | 强度极高但边际改善放缓，拥挤风险上升 |
| 分歧 | 内部分化或炸板上升，仍有核心承接 |
| 退潮 | 广度、强度、持续性和资金多数转弱 |

| 题材 | 生命周期 | 广度证据 | 强度证据 | 持续性证据 | 资金证据 | 反证 |
|---|---|---|---|---|---|---|
| {{theme}} | {{stage}} | {{breadth}} | {{strength}} | {{persistence}} | {{flow}} | {{counter_evidence}} |

## 龙虎榜事实

只陈述榜单和机构统计接口实际返回的内容；不得由席位名称推断未披露身份。

| 标的 | 上榜事实 | 机构统计 | 可支持的有限结论 | 证据 |
|---|---|---|---|---|
| {{stock}} | {{detail}} | {{institution}} | {{bounded_conclusion}} | {{evidence_id}} |

## 次日研究清单

| 研究对象 | 入选依据 | 次日待确认 | 删除条件 | 证据 |
|---|---|---|---|---|
| {{object}} | {{reason}} | {{confirm}} | {{remove}} | {{evidence_id}} |

## 数据来源

| 证据 | 数据集 | 目标日期 | 来源接口 | 采集时间 | 校验 |
|---|---|---|---|---|---|
| {{evidence_id}} | {{dataset}} | {{target_date}} | {{source}} | {{retrieved_at}} | 通过 |
