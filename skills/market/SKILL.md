---
name: market
description: Query A-share market overview, rankings, limit-up pools, concept/industry fund flows, individual stock profile (realtime, kline with multi-period, cyq cost distribution, institution comments, individual fund flow, financials), individual stock news, and save market reviews. A股市场行情查询与深度分析工具，支持大盘、个股走势、涨停板及资金流向。
---

# Market Skill

This skill provides utilities to query real-time and historical Chinese A-share market data, compile individual stock profiles, and save market reviews.

## Environment Setup

Before using this skill, check if the local virtual environment `.venv` exists. If not, initialize it using `uv`:
```bash
# Create the local virtual environment
uv venv skills/market/.venv

# Install required dependencies into the local virtual environment
uv pip install --python skills/market/.venv -r skills/market/requirements.txt
```

## Usage Guidelines

- Run all scripts from the project root `/Users/xiaobaitu/github.com/choseStock` using the skill's local virtual environment python: `skills/market/.venv/bin/python`.
- All scripts output plain text, markdown tables, or JSON. No `rich` terminal library is used, making it easy for you to parse.

## Script References

### 1. Market Overview (`skills/market/scripts/overview.py`)
Show a broad overview of the A-share market (e.g., indices, general up/down stats).
```bash
skills/market/.venv/bin/python skills/market/scripts/overview.py
```

### 2. Market Ranking (`skills/market/scripts/ranking.py`)
Show top gainer or loser stocks.
- `--top N`: Number of stocks to list (default: 10)
- `--type up|down`: Filter by gainers or losers (default: up)
```bash
skills/market/.venv/bin/python skills/market/scripts/ranking.py --top 15 --type down
```

### 3. Limit-Up Pool (`skills/market/scripts/limit_up.py`)
Show details of the limit-up pool.
- `--date YYYYMMDD`: Limit-up pool date (default: today's date)
```bash
skills/market/.venv/bin/python skills/market/scripts/limit_up.py --date 20260618
```

### 4. Fund Flow (`skills/market/scripts/fund_flow.py`)
Analyze capital flows into concepts, industries, or big deals.
- `--type concept|industry|bigdeal`: Cash flow sector type (default: concept)
- `--period 1|3|5`: Period in days (1, 3, or 5 days) (default: 1)
```bash
skills/market/.venv/bin/python skills/market/scripts/fund_flow.py --type industry --period 5
```

### 5. Individual Stock Profile (`skills/market/scripts/stock_profile.py`)
Compile deep-dive information for a specific stock.
- `<code-or-symbol>`: Stock code (6 digits, e.g., `600519`, `000001`)
- `--mode realtime|kline|cyq|comment|fundflow|financials|technical`: Analysis mode (default: realtime). `technical` mode calculates and displays 20+ indicators (MACD, RSI, KDJ, BOLL, ATR, CCI, WR, VWMA, MFI, etc.).
- `--period daily|weekly|monthly|yearly|30min|60min|120min`: Kline period (for `kline` mode, default: daily)
- `--days N`: Show past N data points/days for time-series modes (default: 10)
- `--type income|balance_sheet|cashflow`: Financial report type (for `financials` mode, default: income)
- `--source auto|sina|eastmoney|xueqiu`: Specify the quote source for realtime mode (default: auto). Automatically falls back to Sina/Eastmoney if Xueqiu fails.
- `--token TOKEN`: Manually pass a Xueqiu `xq_a_token` to authenticate Xueqiu queries if necessary.
```bash
skills/market/.venv/bin/python skills/market/scripts/stock_profile.py 600519 --mode kline --period weekly --days 20
skills/market/.venv/bin/python skills/market/scripts/stock_profile.py 000001 --mode cyq --days 5
skills/market/.venv/bin/python skills/market/scripts/stock_profile.py 600519 --mode technical --days 5
skills/market/.venv/bin/python skills/market/scripts/stock_profile.py 600519 --mode realtime --source xueqiu --token "YOUR_TOKEN"
```

### 6. Stock News (`skills/market/scripts/news.py`)
Fetch the latest news for a specific stock.
- `<code>`: Stock code (6 digits)
- `--n N`: Number of news items to fetch (default: 10)
```bash
skills/market/.venv/bin/python skills/market/scripts/news.py 600519 --n 5
```

### 7. Save Review (`skills/market/scripts/save_review.py`)
Format and save a market review to the local directory `data/review/`.
- `--type noon|evening`: Save noon review or evening review
- Input markdown text is passed via standard input or typed as prompt.
```bash
skills/market/.venv/bin/python skills/market/scripts/save_review.py --type evening
```

## Recommended Workflow Scenarios

For a step-by-step guideline of market scenarios (Pre-market, Noon, Evening, Stock Deep-dive), refer to [scenarios.md](file:///Users/xiaobaitu/github.com/choseStock/skills/market/references/scenarios.md).

## Supplemental Data Sources (数据与新闻补充来源)

When you are acting as an agent using this skill, you can consult the following websites as supplemental data and news sources to support your analysis:
- **巨潮资讯网 (Cninfo)**: [https://www.cninfo.com.cn/new/index](https://www.cninfo.com.cn/new/index) - Official information disclosure platform for Chinese listed companies. Excellent for checking official stock announcements, prospectuses, and regular financial statements.
- **同花顺财经 (10jqka)**: [https://www.10jqka.com.cn/](https://www.10jqka.com.cn/) - Real-time market terminal, industry rankings, heatmaps, and capital flows.
- **东方财富 (Eastmoney)**: [https://www.eastmoney.com/default.html](https://www.eastmoney.com/default.html) - Individual stock profiles, financial databases, stock forums (guba), and historical charts.
- **财联社 (CLS)**: [https://www.cls.cn/](https://www.cls.cn/) - Professional real-time financial news, flash news, and macro policy feeds.
- **天天基金网 (Eastmoney Fund)**: [https://www.1234567.com.cn/](https://www.1234567.com.cn/) - Detailed fund holdings, net asset values, historical performance, and index trends.
