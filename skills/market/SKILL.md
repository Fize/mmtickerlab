---
name: market
description: 获取经过日期、时效和完整性校验的 A 股市场与个股 JSON 数据。用于市场快照、指数、涨跌停、行业/概念资金流、龙虎榜、隔夜市场、自选股、个股行情、K 线、技术指标、筹码、情绪、个股资金、财务和新闻查询。只返回数据，不生成市场结论、报告或交易建议。
---

# Market Data

本技能只负责采集、校验和输出数据。所有命令从项目根目录运行，stdout 只包含一个 JSON 文档；重试和供应商诊断写入 stderr。全市场快照、板块资金流、大单和完整财务报表落盘后返回紧凑视图与 `raw.path`，需要明细时按路径局部读取。不要根据数据在本技能内生成主线、周期、买卖或仓位结论。

## 环境

```bash
uv venv skills/market/.venv
uv pip install --python skills/market/.venv -r skills/market/requirements.txt
```

统一入口：

```bash
skills/market/.venv/bin/python skills/market/scripts/market_data.py DATASET --date YYYYMMDD
```

任一命令返回非零状态时，读取错误并停止使用该数据，不把缺失数据解释为空数据。

## 市场数据

```bash
# 交易日历与证券主表
skills/market/.venv/bin/python skills/market/scripts/market_data.py calendar --date YYYYMMDD --count 10
skills/market/.venv/bin/python skills/market/scripts/market_data.py master --date YYYYMMDD

# 七个主要指数；午间行标记 intraday，收盘行标记 final
skills/market/.venv/bin/python skills/market/scripts/market_data.py indices --date YYYYMMDD --session noon --count 60
skills/market/.venv/bin/python skills/market/scripts/market_data.py indices --date YYYYMMDD --session close --count 60

# 全市场明细、宽度、涨跌分布和同快照排行
skills/market/.venv/bin/python skills/market/scripts/market_data.py snapshot --date YYYYMMDD --session noon
skills/market/.venv/bin/python skills/market/scripts/market_data.py snapshot --date YYYYMMDD --session close

# 涨停、炸板、跌停、连板梯队和行业分布
skills/market/.venv/bin/python skills/market/scripts/market_data.py limits --date YYYYMMDD --session close

# 行业/概念 1、3、5 日完整资金排行及流入/流出 Top 20
skills/market/.venv/bin/python skills/market/scripts/market_data.py flows --date YYYYMMDD --session close

# 当日大单、龙虎榜和隔夜市场
skills/market/.venv/bin/python skills/market/scripts/market_data.py big-deals --date YYYYMMDD
skills/market/.venv/bin/python skills/market/scripts/market_data.py lhb --date YYYYMMDD
skills/market/.venv/bin/python skills/market/scripts/market_data.py overnight --date YYYYMMDD
```

`snapshot`、`flows` 只能在当天午间 11:30-13:00 或收盘 15:05 后采集。龙虎榜只能在当天 16:30 后采集。`overnight`、实时行情和当前证券主表不能回填历史日期。分钟线按目标日期截断。

## 个股数据

需要个股代码的数据集必须传 `--code`：

```bash
# 实时行情
skills/market/.venv/bin/python skills/market/scripts/market_data.py quote --date YYYYMMDD --code 600519

# 日、周、月和 30/60/120 分钟 K 线
skills/market/.venv/bin/python skills/market/scripts/market_data.py kline --date YYYYMMDD --code 600519 --period daily --count 120 --adjust qfq

# 纯技术指标数值，至少使用 250 行预热数据
skills/market/.venv/bin/python skills/market/scripts/market_data.py technical --date YYYYMMDD --code 600519 --count 10 --adjust qfq

# 筹码、情绪和多周期个股资金
skills/market/.venv/bin/python skills/market/scripts/market_data.py chips --date YYYYMMDD --code 600519 --count 10
skills/market/.venv/bin/python skills/market/scripts/market_data.py sentiment --date YYYYMMDD --code 600519 --count 10
skills/market/.venv/bin/python skills/market/scripts/market_data.py stock-flow --date YYYYMMDD --code 600519 --flow-period 5

# 财务报表与原始新闻
skills/market/.venv/bin/python skills/market/scripts/market_data.py financials --date YYYYMMDD --code 600519 --statement income --count 4
skills/market/.venv/bin/python skills/market/scripts/market_data.py news --date YYYYMMDD --code 600519 --count 10
```

技术指标只表示计算结果；筹码成本不是必然支撑位；资金流不代表可识别的机构身份；新闻保持原文数据，不在本技能内总结或解释。财务数据默认返回常用字段，完整报表位于 `raw.path`。

## 自选股

`data/watchlist.json` 可为代码数组或带 `stocks` 的对象。批量获取最多 250 日 K 线和最近技术指标：

```bash
skills/market/.venv/bin/python skills/market/scripts/market_data.py watchlist --date YYYYMMDD --count 250
```

未配置自选股时返回 `configured: false`，不是错误。
已配置时每只股票独立返回 `ready`、`insufficient_history`、`stale`、`no_data` 或 `provider_error`，单只股票不会阻断其他标的。

## 使用场景

完整的数据组合和限制见 [references/scenarios.md](references/scenarios.md)。`plan-review` 负责组装盘前、盘中和盘后数据；最终分析与报告由 Agent 根据这些数据完成。
