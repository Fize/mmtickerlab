---
name: plan-review
description: |
  Standardized pre-market preparation, noon review, and evening review workflows plus trading journal management.
  三段式交易操作系统：盘前准备→午间复盘→晚间复盘，配合交易日志工具记录每一天。
  触发词：盘前准备、午间复盘、晚间复盘、交易计划、复盘、写日志、交易日志、今日计划、纪律打分。
  ——核心原则：脚本取数据，AI 做分析，交易者负责最终决策。
---

# Plan & Review Skill

> 交易操作系统：没有计划不交易，没有复盘不成长。

This skill provides the **process backbone** for the mmtickerlab project. It connects the `market` data skill and `sim-trade` execution skill into a disciplined daily workflow.

**Architecture principle**: Scripts are **data faucets** — they fetch, aggregate, and structure raw market data. The AI is the **analyst** — it reads the data, applies reasoning, identifies patterns, and generates the final trading plan. This separation ensures analysis is contextual and adaptive, not hard-coded.

There are three daily checkpoints:

| Checkpoint | Who fetches data | Who analyzes |
|:---|:---|:---|
| **Pre-Market** (盘前准备) | `pre_market.py` | AI synthesizes plan |
| **Noon Review** (午间复盘) | `noon_review.py` | AI checks alignment |
| **Evening Review** (晚间复盘) | `evening_review.py` | AI performs deep复盘 |

**The central artifact is the daily trading journal**, stored at `data/journal/YYYYMMDD.md`.

---

## Environment Setup

```bash
uv venv skills/plan-review/.venv
uv pip install --python skills/plan-review/.venv -r skills/plan-review/requirements.txt
```

---

## Data Faucet Scripts (all in `skills/market/scripts/`)

These scripts fetch and structure raw data. They do NOT make final trading decisions — that's the AI's job.

### `pre_market.py` — 盘前数据聚合器

Fetches all pre-market data into structured output. Run first, then AI analyzes.

```bash
skills/market/.venv/bin/python skills/market/scripts/pre_market.py [--date YYYYMMDD]
```

**Data provided**:

| Section | Data |
|:---|:---|
| A50期货 | 最新价 + 涨跌幅 |
| 离岸人民币 | USD/CNY 买卖报价 |
| 美股三大指数 | DJIA/SPX/NDX 收盘价 + 涨跌幅 |
| 恒生指数 | 收盘价 + 涨跌幅 |
| 宏观新闻 | 政策/经济相关新闻标题 + 摘要 |
| 7大A股指数 | 收盘价 + 涨跌幅 |
| 市场宽度 | 涨跌家数、涨停/跌停数、成交额 |
| 涨停池 Top 15 | 代码/名称/连板/行业/换手率 |
| 概念资金流向 Top 5 | 净流入/涨幅/领涨股 |
| 行业资金流向 Top 5 | 净流入/涨幅/领涨股 |
| 自选股技术指标 | K线 + MA/MACD/RSI/BOLL/KDJ（每只） |

### `noon_review.py` — 午间数据聚合器

```bash
skills/market/.venv/bin/python skills/market/scripts/noon_review.py
```

**Data provided**:
- 早盘实时三大指数
- 涨跌分布 + 涨停/跌停/炸板率
- 领涨题材 + 大单成交
- 盘前计划标的实时报价（从 journal 解析）

### `evening_review.py` — 晚间数据聚合器

```bash
skills/market/.venv/bin/python skills/market/scripts/evening_review.py [--date YYYYMMDD]
```

**Data provided**:
- 全天市场总览（同 pre_market 模块二）
- 主线题材资金流向
- **龙虎榜**：机构买卖/游资动向/负反馈标的（`stock_lhb_detail_em` + `stock_lhb_ggtj_sina`）
- 连板高度 + 阶梯完整性

---

## Journal Script

### `journal.py` (`skills/plan-review/scripts/journal.py`)

| Command | Description |
|:---|:---|
| `create` | Create today's journal (reads plan from `--plan` or stdin) |
| `append --section {noon,evening}` | Append a review section |
| `view [--date YYYYMMDD]` | View a journal |
| `list [--n N]` | List recent entries |

---

## Daily Workflows

### Phase 1: Pre-Market Preparation (盘前准备)

**Goal**: Generate a complete, AI-analyzed trading plan before market opens.

#### Step 1: Fetch Raw Data

```bash
skills/market/.venv/bin/python skills/market/scripts/pre_market.py > /tmp/pre_market_data.md
```

This produces a structured data dump. The AI reads it.

#### Step 2: AI Analysis & Plan Synthesis

The AI reads the data and performs the following analysis:

**模块一：宏观定调**
- Read A50 + US indices + RMB + news
- Judge: 今日高开/平开/低开概率？外资情绪偏多/偏空？有无重大政策催化剂？
- Output: 1-2 句宏观定调 + 对仓位的影响

**模块二：情绪判断**
- Read breadth data (涨跌比、涨停/跌停数、成交额)
- Read 涨停池（连板分布、行业集中度）
- Read 资金流向（概念/行业 Top 5）
- Judge: 赚钱效应在哪里？亏钱效应在哪里？连板梯队是否健康？
- Output: 情绪定性 + 最强 1-2 条主线

**模块三：题材筛选**
- Cross-reference 资金流向 + 涨停集中行业 + 宏观新闻
- Judge: 哪些题材有持续性？哪些是一日游？
- Output: ≤3 个焦点题材，每个含：逻辑 + 龙头

**模块四：交易预案（核心）**
- Read 自选股技术指标数据
- For each stock, the AI judges:
  - 当前处于什么技术位置？（趋势/震荡/超跌）
  - 有哪些可识别的入场信号？信号的可靠性如何？
  - 合理的入场价位、止损价位、仓位比例？
- **If no clear setups exist, state "今日无符合条件的交易机会"** — this is a valid output.
- Output: ≤3 个 If-Then 预案

**模块五：仓位纪律**
- Based on 模块一+二, AI judges market temperature
- Determines position limit
- Writes today's prohibited behaviors

#### Step 3: Save to Journal

```bash
# AI writes the final plan to a temp file, then:
cat /tmp/final_plan.md | skills/plan-review/.venv/bin/python skills/plan-review/scripts/journal.py create
```

> ### ✅ Pre-Market Completion Criterion
> Journal contains AI-generated plan with all 5 modules. **No plan = no trading.**

---

### Phase 2: Noon Review (午间复盘)

**Goal**: Check if the morning is going according to plan.

#### Step 1: Fetch Noon Data

```bash
skills/market/.venv/bin/python skills/market/scripts/noon_review.py > /tmp/noon_data.md
```

#### Step 2: AI Analysis

1. **Read the market**: 上午指数表现？成交量 vs 昨日同期？领涨/领跌板块？
2. **Check against plan**: Read today's journal. For each plan stock, check:
   - Did trigger conditions fire?
   - If not, are conditions still valid?
   - Any stock showing unexpected weakness?
3. **Self-examination check**: Any plan-external impulses?
4. **Afternoon strategy**: Based on morning patterns, what's the afternoon play?

#### Step 3: Save

```bash
cat /tmp/noon_final.md | skills/plan-review/.venv/bin/python skills/plan-review/scripts/journal.py append --section noon
```

---

### Phase 3: Evening Review (晚间复盘)

**Goal**: Deep复盘 — market playback, self-scoring, and next-day preparation.

#### Step 1: Fetch Evening Data

```bash
skills/market/.venv/bin/python skills/market/scripts/evening_review.py > /tmp/evening_data.md
```

This provides: full-day breadth, theme flows, 龙虎榜 data, 连板高度.

#### Step 2: AI Deep Analysis

**① Market Narrative**: What was today's dominant story? One sentence.

**② Theme Lifecycle**: The AI judges each leading theme's stage:
- 启动期 / 发酵期 / 高潮 / 分歧 / 退潮
- This is NOT a formula — the AI considers volume, breadth, news context, sector rotation patterns

**③ LHB Analysis**: Read 龙虎榜 data and identify:
- Which institutions are buying? What's the pattern?
- Any stocks with asymmetric buy/sell ratios?
- Any warning signals (机构集体出逃)?

**④ Candidate Pool**: The AI generates 3-5 next-day candidates. For each:
- **Why**: Concrete reason grounded in today's data (LHB buying + technical position + theme alignment)
- **Risk**: What could go wrong?
- **Watch level**: 重点关注 / 一般关注
- This is raw material for tomorrow's pre_market.py, not trading instructions

**⑤ Self-Scoring**:
- P&L attribution (planned vs unplanned)
- Discipline score (0-100)
- One error logged

#### Step 3: Save

```bash
cat /tmp/evening_final.md | skills/plan-review/.venv/bin/python skills/plan-review/scripts/journal.py append --section evening
```

> ### ✅ Evening Review Completion Criterion
> Journal contains: 1) market narrative, 2) theme lifecycle judgment, 3) LHB analysis, 4) candidate pool with reasoning, 5) discipline score + error log.

---

## AI Analysis Guidelines

When performing analysis, the AI should:

1. **Ground every judgment in data**: "Because 涨停 131 家 and 半导体净流入 119 亿..." not "半导体 looks strong"
2. **State uncertainty explicitly**: "炸板率 59% suggests high分歧 but 131 涨停 still indicates strong underlying demand — the signal is mixed"
3. **Quality over quantity**: 3 well-analyzed candidates > 10 superficial mentions
4. **"No trade" is a valid output**: If conditions aren't right, say so clearly
5. **Override script suggestions when needed**: The scripts provide baseline analysis for efficiency. If the AI disagrees, explain why and provide its own judgment

---

## Integration with Existing Skills

| Skill | Role |
|:---|:---|
| `market` | **Data faucet**: `pre_market.py`, `noon_review.py`, `evening_review.py`, plus individual scripts (`overview.py`, `limit_up.py`, `fund_flow.py`, `stock_profile.py`, `news.py`) |
| `sim-trade` | **Execution**: portfolio check (pre-market), trade verification (evening) |

---

## Data Locations

| Data | Path |
|:---|:---|
| Daily journals | `data/journal/YYYYMMDD.md` |
| Output templates | `skills/plan-review/templates/*.md` |
| Data scripts | `skills/market/scripts/pre_market.py`, `noon_review.py`, `evening_review.py` |
| Skill scripts | `skills/plan-review/scripts/journal.py` |
| Watchlist | `data/watchlist.json` |
