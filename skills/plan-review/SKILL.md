---
name: plan-review
description: |
  Standardized pre-market preparation, noon review, and evening review workflows plus trading journal management.
  三段式交易操作系统：盘前准备→午间复盘→晚间复盘，配合交易日志工具记录每一天。
  触发词：盘前准备、午间复盘、晚间复盘、交易计划、复盘、写日志、交易日志、今日计划、纪律打分。
  ——核心原则：模板定结构，prompt 定框架，AI 按需用 market 脚本取真实数据做分析，交易者负责最终决策。
---

# Plan & Review Skill

> 交易操作系统：没有计划不交易，没有复盘不成长。

This skill provides the **process backbone** for the mmtickerlab project. It connects the `market` data skill and `sim-trade` execution skill into a disciplined daily workflow.

**Architecture principle**: Templates define the structure, prompts define the analysis framework, and AI uses `market` skill scripts on-demand to fetch real data. This ensures analysis is grounded in actual market data, not fabricated.

There are three daily checkpoints:

| Checkpoint | Who fetches data | Who analyzes |
|:---|:---|:---|
| **Pre-Market** (盘前准备) | AI via `market` scripts | AI synthesizes plan |
| **Noon Review** (午间复盘) | AI via `market` scripts | AI checks alignment |
| **Evening Review** (晚间复盘) | AI via `market` scripts | AI performs deep复盘 |

**Output**: Reports are saved to `report/` in the project root. Filename format: `YYYYMMDD_盘前计划.md`, `YYYYMMDD_午间复盘.md`, `YYYYMMDD_晚间复盘.md`. If the user specifies an output location, use that instead.

---

## Environment Setup

```bash
uv venv skills/plan-review/.venv
uv pip install --python skills/plan-review/.venv -r skills/plan-review/requirements.txt
```

---

## Data Sources

Plan-review 不运行数据获取脚本。数据由 AI 通过 `market` skill 的查询脚本按需获取：

| 数据需求 | market skill 脚本 | 用途 |
|:---|:---|:---|
| 全球指数 + A50 | `overview.py` | 宏观定调 |
| 市场涨跌 + 涨停跌停 | `overview.py` / `limit_up.py` | 情绪判断 |
| 概念/行业资金流向 | `fund_flow.py` | 题材筛选 |
| 个股技术指标 | `stock_profile.py --mode technical` | 交易预案 |
| 个股实时行情 | `stock_profile.py --mode realtime` | 午间对齐 |
| 个股新闻 | `news.py` | 消息面补充 |
| 龙虎榜* | — | 晚间复盘需要，需 AI 浏览外部数据源 |

> *龙虎榜数据在 16:30-17:00 后才发布，晚间复盘时通过财联社等网站获取。

---

## Daily Workflows

### Phase 1: Pre-Market Preparation (盘前准备)

**Goal**: 开盘前生成完整的交易计划。

**模块一：宏观定调**
AI 按需运行 `overview.py`（获取全球指数）+ `news.py`（宏观新闻），分析：
- 今日高开/平开/低开概率？外资情绪偏多/偏空？
- Output: 1-2 句宏观定调

**模块二：情绪判断**
AI 按需运行 `overview.py`（涨跌分布）+ `limit_up.py`（涨停池）+ `fund_flow.py`（资金流向），分析：
- 赚钱效应在哪里？连板梯队是否健康？
- Output: 情绪定性 + 最强 1-2 条主线

**模块三：题材筛选**
AI 交叉分析资金流向 + 涨停行业 + 宏观新闻：
- 哪些题材有持续性？哪些是一日游？
- Output: ≤3 个焦点题材

**模块四：交易预案（核心）**
AI 按需运行 `stock_profile.py --mode technical` 获取自选股技术指标，分析：
- 当前技术位置？入场信号？止损价位？
- **If no clear setups, state "今日无符合条件的交易机会"**
- Output: ≤3 个 If-Then 预案

**模块五：仓位纪律**
基于宏观和情绪，AI 判断仓位上限。

**输出**：将完整交易计划写入 `report/YYYYMMDD_盘前计划.md`（或用户指定的路径）。

> ✅ **Pre-Market Completion Criterion**: Journal 含完整 5 模块。**No plan = no trading.**

---

### Phase 2: Noon Review (午间复盘)

**Goal**: 检查上午走势是否符合计划。

AI 按需运行 `overview.py`（午间指数）+ `stock_profile.py --mode realtime`（计划标的实时价）：
1. 上午指数表现？成交量 vs 昨日？
2. 对照计划检查每个标的：触发条件了吗？有异常走弱吗？
3. 午间冲动检查
4. 下午策略

**输出**：将复盘写入 `report/YYYYMMDD_午间复盘.md`（或用户指定的路径）。

---

### Phase 3: Evening Review (晚间复盘)

**Goal**: 深度复盘——市场回放、自我打分、次日准备。

AI 综合分析当日数据：
1. **Market Narrative**: 今日主导故事，一句话
2. **Theme Lifecycle**: 主导题材所处阶段（启动/发酵/高潮/分歧/退潮）
3. **LHB Analysis**: 机构买卖/游资动向（通过财联社等外部数据源）
4. **Candidate Pool**: 3-5 个次日候选，含技术理由 + 风险提示
5. **Self-Scoring**: P&L 归因 + 纪律打分（0-100）+ 一条错误记录

**输出**：将复盘写入 `report/YYYYMMDD_晚间复盘.md`（或用户指定的路径）。

> ✅ **Evening Review Completion Criterion**: Journal 含市场回顾、题材判断、候选池、纪律打分。

---

## AI Analysis Guidelines

When performing analysis, the AI should:

1. **Ground every judgment in data**: "Because 涨停 131 家 and 半导体净流入 119 亿..." not "半导体 looks strong"
2. **State uncertainty explicitly**: "炸板率 59% suggests high分歧 but 131 涨停 still indicates strong underlying demand — the signal is mixed"
3. **Quality over quantity**: 3 well-analyzed candidates > 10 superficial mentions
4. **"No trade" is a valid output**: If conditions aren't right, say so clearly

### ⛔ 数据真实性红线（硬性约束）

5. **数据必须来自 market skill 脚本或外部可靠数据源**：每个数字必须能在已运行的脚本输出或用户提供的材料中找到来源。**禁止使用模型内部知识生成数值**。

6. **无数据 = 停止分析**：

   | 情况 | 必须输出的内容 |
   |:---|:---|
   | 股票技术指标数据获取失败 | "技术数据不可用，无法对该标的进行分析" |
   | 龙虎榜数据未发布 | "龙虎榜数据通常在 16:30-17:00 后发布，当前尚未就绪" |
   | 涨停池数据为空但为交易日 | "今日涨停数据未能成功获取，无法生成分析" |

7. **绝对禁止编造**：
   - 具体股票的成交价、买卖盘口
   - 龙虎榜机构的买入/卖出金额
   - 涨停股池的具体成分股名单
   - 均线、MACD、KDJ 等任何技术指标的数值
   - 资金流向净额的具体数值

8. **不确定就说不知道**：遇到数据不完整、信息不充分的情况，明确告知用户，不得填补空白。

---

## Integration with Existing Skills

| Skill | Role |
|:---|:---|
| `market` | **Data source**: `overview.py`, `limit_up.py`, `fund_flow.py`, `stock_profile.py`, `news.py` — AI invokes these on-demand to fetch real market data |
| `sim-trade` | **Execution**: portfolio check (pre-market), trade verification (evening) |

---

## Data Locations

| Data | Path |
|:---|:---|
| Trading reports | `report/YYYYMMDD_{盘前计划,午间复盘,晚间复盘}.md` |
| Output templates | `skills/plan-review/templates/*.md` |
| Watchlist | `data/watchlist.json` |
