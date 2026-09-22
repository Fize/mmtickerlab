---
name: market
description: 获取经过日期、时效和完整性校验的 A 股/港美股原始行情与量化数据。支持查询实时报价、多周期 K 线、20+ 项确定性技术指标、涨跌停池、资金流向、大单异动、筹码分布、财务三大表及资讯新闻。当用户需要查询股票数据、获取实时行情、绘制 K 线图表、计算技术指标或检索财务数据时触发（包含触发词：查行情, 查K线, 查指标, 涨跌停池, 资金流向, 龙虎榜, 筹码分布, 财务报表, market data, stock quote, kline）。
metadata:
  openclaw:
    requires:
      bins:
        - python3
---

# Market Data

本技能只负责采集、校验和输出数据。所有命令从项目根目录运行，stdout 只包含一个 JSON 文档；重试和供应商诊断写入 stderr。全市场快照、板块资金流、大单和完整财务报表落盘后返回紧凑视图与 `raw.path`，需要明细时按路径局部读取。不要根据数据在本技能内生成主线、周期、买卖或仓位结论。

本技能可以独立运行，不要求先生成其他 Skill 的报告。数据缺失时可从已配置的供应商或权威交易所来源补充，但必须核验日期、时点、字段、单位和覆盖范围；来源冲突或关键字段仍不可核验时直接阻断，并保留结构化阻断原因。

原始明细是聚合结果的事实基础。现有命令获取到明细时同步写入 `market/data/market_raw.db`；重复内容去重，供应商修订保留为新观察版本。用户查询本地没有的数据时先尝试供应商，只有供应商也无法提供时才阻断。

## 环境

```bash
uv venv market/.venv
uv pip install --python market/.venv -r market/requirements.txt
```

统一入口：

```bash
market/.venv/bin/python market/scripts/market_data.py DATASET --date YYYYMMDD
```

### 数据供应商分工与架构

技能采用**双引擎 + 自动容灾**架构稳定覆盖全市场：

1. **海外标的与跨市场（港股、美股、隔夜指数）**：
   - **主要接口**：采用 `yfinance` 作为第一数据源。
   - **自动容灾**：当遭遇外部频控或网络波动时，自动无缝降级到新浪极速直连源（毫秒级响应）及 AKShare 历史日 K 接口，并在输出中透明标注数据源。
2. **A 股特色数据集（涨跌停池、连板梯队、龙虎榜、板块资金流、A 股交易日历）**：
   - **主要接口**：由加固版 `AKShare` 承载，提供完整的涨跌停炸板、连板高度与大单席位数据。

任一命令返回非零状态时，读取错误并停止使用该数据，不把缺失数据解释为空数据。

## 多市场与标的代码约定

```bash
# 交易日历与证券主表
market/.venv/bin/python market/scripts/market_data.py calendar --date YYYYMMDD --count 10
market/.venv/bin/python market/scripts/market_data.py master --date YYYYMMDD

# 七个主要指数；午间行标记 intraday，收盘行标记 final
market/.venv/bin/python market/scripts/market_data.py indices --date YYYYMMDD --session noon --count 60
market/.venv/bin/python market/scripts/market_data.py indices --date YYYYMMDD --session close --count 60

# 全市场明细、宽度、涨跌分布和同快照排行
market/.venv/bin/python market/scripts/market_data.py snapshot --date YYYYMMDD --session noon
market/.venv/bin/python market/scripts/market_data.py snapshot --date YYYYMMDD --session close

# 涨停、炸板、跌停、连板梯队和行业分布
market/.venv/bin/python market/scripts/market_data.py limits --date YYYYMMDD --session close

# 行业/概念 1、3、5 日完整资金排行及流入/流出 Top 20
market/.venv/bin/python market/scripts/market_data.py flows --date YYYYMMDD --session close

# 当日大单、龙虎榜和隔夜市场
market/.venv/bin/python market/scripts/market_data.py big-deals --date YYYYMMDD
market/.venv/bin/python market/scripts/market_data.py lhb --date YYYYMMDD
market/.venv/bin/python market/scripts/market_data.py overnight --date YYYYMMDD

# 核心商品期货行情（贵金属、有色、黑色、能源、农业、新能源材料）
market/.venv/bin/python market/scripts/market_data.py commodities --date YYYYMMDD
```

`snapshot`、`flows` 只能在当天午间 11:30-13:00 或收盘 15:05 后采集。龙虎榜只能在当天 16:30 后采集。`overnight`、`commodities`、实时行情和当前证券主表不能回填历史日期。分钟线按目标日期截断。商品行情必须保留具体品种、单位、时间戳和交易状态；缺少核心品种时命令阻断。

恐慌贪婪指数的计算工具位于 `plan-review/scripts/derived_metrics.py`，版本为 `fg-v1`；`market` 只提供其底层行情，不在数据技能内生成市场定性结论。

稀土目前没有统一的国内稀土期货主连合约，报告应单独接入并标记稀土现货报价，不得把现货价格伪装成期货行情。

## 个股数据

需要个股代码的数据集必须传 `--code`：

```bash
# 实时行情
market/.venv/bin/python market/scripts/market_data.py quote --date YYYYMMDD --code 600519

# 日、周、月和 30/60/120 分钟 K 线
market/.venv/bin/python market/scripts/market_data.py kline --date YYYYMMDD --code 600519 --period daily --count 120 --adjust qfq

# 纯技术指标数值，至少使用 250 行预热数据
market/.venv/bin/python market/scripts/market_data.py technical --date YYYYMMDD --code 600519 --count 10 --adjust qfq

# 筹码、情绪和多周期个股资金
market/.venv/bin/python market/scripts/market_data.py chips --date YYYYMMDD --code 600519 --count 10
market/.venv/bin/python market/scripts/market_data.py sentiment --date YYYYMMDD --code 600519 --count 10
market/.venv/bin/python market/scripts/market_data.py stock-flow --date YYYYMMDD --code 600519 --flow-period 5

# 财务报表与原始新闻
market/.venv/bin/python market/scripts/market_data.py financials --date YYYYMMDD --code 600519 --statement income --count 4
market/.venv/bin/python market/scripts/market_data.py news --date YYYYMMDD --code 600519 --count 10
```

技术指标只表示计算结果；筹码成本不是必然支撑位；资金流不代表可识别的机构身份；新闻保持原文数据，不在本技能内总结或解释。财务数据默认返回常用字段，完整报表位于 `raw.path`。

## 原始明细查询

使用 `raw --kind KIND` 查询聚合前的明细。可用类型：

- `trading-calendar`、`security-master`、`index-bar`；
- `market-quote`、`stock-quote`、`stock-bar`；
- `limit-up`、`limit-break`、`limit-down`、`sector-flow`、`large-trade`；
- `dragon-tiger`、`dragon-tiger-institution`；
- `chip`、`sentiment`、`stock-flow`、`financial`、`news`、`overnight`。

按时间点或范围查询：

```bash
market/.venv/bin/python market/scripts/market_data.py raw --date 20260813 --kind stock-bar --code 600519 --period 30 --at 20260813T143000 --count 80
market/.venv/bin/python market/scripts/market_data.py raw --date 20260813 --kind market-quote --at 20260813T143000 --count 6000
market/.venv/bin/python market/scripts/market_data.py raw --date 20260813 --kind limit-up --from 20260813T093000 --to 20260813T150000 --count 200
```

`--at` 与 `--from/--to` 不能同时使用。查询先读取本地原始库；数据不足时自动调用对应供应商并保存结果。实时接口无法回填且本地从未采集的历史截面必须返回阻断，不用当前数据替代。

## 指定时点技术指标

`technical` 支持日、周、月和 30/60/120 分钟周期，并可选择指标：

```bash
market/.venv/bin/python market/scripts/market_data.py technical --date 20260813 --code 600519 --period 30 --at 20260813T143000 --indicator SMA_20,MACD,RSI_6 --count 20
```

先使用原始库中 `--at` 以前的 K 线；少于 250 根预热数据时才请求供应商。盘中查询日线指标时排除当日尚未完成的日 K，禁止未来数据进入计算。响应中的 `data_basis` 表明使用 `raw_store` 还是 `provider`。

## 自选股

`data/watchlist.json` 可为代码数组或带 `stocks` 的对象。批量获取最多 250 日 K 线和最近技术指标：

```bash
market/.venv/bin/python market/scripts/market_data.py watchlist --date YYYYMMDD --count 250
```

未配置自选股时返回 `configured: false`，不是错误。
已配置时每只股票独立返回 `ready`、`insufficient_history`、`stale`、`no_data` 或 `provider_error`，单只股票不会阻断其他标的。

## 使用场景

完整的数据组合和限制见 [references/scenarios.md](references/scenarios.md)。`plan-review` 负责组装盘前、盘中和盘后数据；最终分析与报告由 Agent 根据这些数据完成。
