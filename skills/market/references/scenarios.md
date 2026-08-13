# Market Data Scenarios

Market 只返回数据。以下组合说明 Agent 在不同问题中应获取哪些数据，不预设分析结论。

| 场景 | 必需数据 | 可选补充 | 主要限制 |
|---|---|---|---|
| 快速市场状态 | `indices`、`snapshot` | `limits`、`flows` | 使用同一阶段快照 |
| 盘前研究 | `calendar`、前收 `indices/snapshot/limits/flows`、`overnight` | `watchlist`、个股新闻 | 不用实时值回填前收 |
| 午间复核 | 前收数据、午间 `indices/snapshot/limits/flows` | `big-deals`、自选股 `quote/kline` | 仅在 11:30-13:00 采集 |
| 盘后复盘 | 午间数据、收盘 `indices/snapshot/limits/flows`、独立 `lhb` | 自选股 `technical` | 15:05 采收盘，16:30 后单独采龙虎榜 |
| 涨跌异动 | `snapshot.data.rankings` | `big-deals`、`news` | 排行只说明极端表现 |
| 题材研究 | 1/3/5 日 `flows`、近五日 `limits` | 题材代表股数据 | 由 Agent 比较广度、强度和资金 |
| 个股趋势 | `kline`、`technical` | `chips`、`stock-flow` | 技术指标不等于交易信号 |
| 个股基本面 | 三类 `financials` | `news` | 区分报告期与获取日期 |
| 个股情绪 | `sentiment`、`stock-flow` | `news`、`big-deals` | 不推断未披露资金身份 |
| 自选股跟踪 | `watchlist` | 当日 `quote`、分钟 `kline` | 只处理配置中的标的 |
| 数据故障诊断 | 对应数据集 JSON、stderr | `akshare_patch` 重试日志 | 不把接口失败解释为零记录 |

## Data Interpretation Boundaries

- `snapshot` 提供全市场明细、分布和排行；市场定性由 Agent 完成。
- `limits` 提供连板梯队和行业计数；题材生命周期由 Agent 完成。
- `flows` 分别提供 1、3、5 日数据；持续性和背离由 Agent 比较。
- `technical` 提供确定性计算值；形态名称和观察条件由 Agent 生成。
- `news` 提供标题、正文、来源、时间和链接；催化剂解释由 Agent 完成。
- `financials` 提供报表原始字段；增长质量和估值判断由 Agent 完成。
- 大型快照的命令结果只携带紧凑视图；完整记录从 `data.raw.path` 按需读取。
