# A-Share Market Analysis Scenarios

Below are recommended workflow sequences for using these tools at different times of the trading day.

| Scenario | Script Sequence | Description |
| :--- | :--- | :--- |
| **盘前 (Pre-Market)** | `overview` → `limit_up --date <yesterday>` → `fund_flow --type concept` → `stock_profile <code-in-watchlist>` | Check overall index state, identify momentum leaders from yesterday, examine leading concept flows, and check watchlist realtimes. |
| **午间 (Noon Break)** | `overview` → `ranking --type up` → `limit_up` → `stock_profile <code> --mode kline --period 30min` → `save_review --type noon` | Look for mid-day leaders, analyze limit-up performance, check individual intraday 30-min trends, and write a noon review. |
| **晚间 (Evening Review)** | `overview` → `ranking` → `limit_up` → `fund_flow --type industry` → `stock_profile <code>` → `save_review --type evening` | Analyze full-day market indices, top gainers/losers, limit-up stocks, industry capital flow, deep-dive into watchlist names, and save evening review. |
| **个股深度 (Stock Deep-Dive)** | `stock_profile <code> --mode kline` → `--mode cyq` → `--mode comment` → `--mode fundflow` → `--mode financials` → `news` | Comprehensive analysis: technical chart (kline), cost support (cyq), sentiment (comment), money flow (fundflow), earnings (financials), and news. |

---

## Example Command Execution

### Evening Review Sequence
1. **Indices and general stats**:
   ```bash
   .venv/bin/python skills/market/scripts/overview.py
   ```
2. **Top gainers**:
   ```bash
   .venv/bin/python skills/market/scripts/ranking.py --top 10 --type up
   ```
3. **Limit-ups list**:
   ```bash
   .venv/bin/python skills/market/scripts/limit_up.py
   ```
4. **Fund flows (Industry)**:
   ```bash
   .venv/bin/python skills/market/scripts/fund_flow.py --type industry --period 1
   ```
5. **Save Review**:
   ```bash
   .venv/bin/python skills/market/scripts/save_review.py --type evening
   ```
