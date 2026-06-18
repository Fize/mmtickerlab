---
name: sim-trade
description: A-share simulation trading tool. Support resetting the portfolio, checking holdings/P&L, buying stocks, selling stocks, and querying transaction history under strict A-share trading rules (T+1, lot size, commissions, stamp tax, trading hours). A股模拟交易工具，支持账户初始化、持仓及盈亏查询、买入、卖出及交易历史查询。
---

# Sim-Trade Skill

This skill provides a complete local paper-trading simulation environment adhering to China's A-share market trading rules.

## Core Rules Implemented

1. **T+1 Settlement**: Stocks purchased today can only be sold on or after the next calendar day. `available_shares` is computed dynamically based on the purchase date.
2. **Lot Size**: Buy orders must be in multiples of 100 shares. Sell orders allow any amount up to `available_shares` (to support odd lots).
3. **Price Limits**: Normal stocks: ±10% limit; ST stocks: ±5% limit; ChiNext (30xxxx) and Star Market (68xxxx): ±20% limit; Beijing Stock Exchange (4xxxxx/8xxxxx): ±30% limit.
4. **Trading Hours**: Orders are only executed during A-share trading hours (9:30-11:30 and 13:00-15:00 on weekdays). Can be bypassed with the `--force` flag.
5. **Trading Fees**:
   - Commission: 0.025% of trade value (minimum ¥5, charged on both buy and sell).
   - Stamp Tax: 0.1% of trade value (charged on sell only).
   - Transfer Fee: 0.002% of trade value (charged on both buy and sell).

## Environment Setup

Before using this skill, check if the local virtual environment `.venv` exists. If not, initialize it using `uv`:
```bash
# Create the local virtual environment
uv venv skills/sim-trade/.venv

# Install required dependencies into the local virtual environment
uv pip install --python skills/sim-trade/.venv -r skills/sim-trade/requirements.txt
```

## Usage Guidelines

- Run all scripts from the project root `/Users/xiaobaitu/github.com/choseStock` using the skill's local virtual environment python: `skills/sim-trade/.venv/bin/python`.
- All account holdings, portfolios, and histories are stored locally inside the skill folder under `skills/sim-trade/data/simulation/`.

## Script References

### 1. Reset Account (`skills/sim-trade/scripts/reset.py`)
Reset or initialize the simulation account.
- `--cash CAPITAL`: Initial capital (default: 500,000 Yuan)
- `--name ACCOUNT_NAME`: Account name (default: "我的模拟账户")
- `--yes`: Skip confirmation prompt (non-interactive fallback)
```bash
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/reset.py --cash 1000000 --name "激进型账户"
```

### 2. View Portfolio (`skills/sim-trade/scripts/portfolio.py`)
View current positions, cash balances, and real-time market value/P&L.
```bash
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/portfolio.py
```

### 3. Buy Stock (`skills/sim-trade/scripts/buy.py`)
Place a buy order for a stock.
- `<code>`: 6-digit stock code (e.g. `600519`)
- `<qty>`: Quantity in shares (must be a multiple of 100)
- `--price PRICE`: Buy price limit. If omitted, executes at the current real-time price.
- `--force`: Bypass trading hours check.
```bash
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/buy.py 600519 100
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/buy.py 000001 200 --price 10.50 --force
```

### 4. Sell Stock (`skills/sim-trade/scripts/sell.py`)
Place a sell order for a stock.
- `<code>`: 6-digit stock code (e.g. `600519`)
- `<qty>`: Quantity in shares (must be <= available shares)
- `--price PRICE`: Sell price limit. If omitted, executes at the current real-time price.
- `--force`: Bypass trading hours check.
```bash
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/sell.py 600519 100
```

### 5. Transaction History (`skills/sim-trade/scripts/history.py`)
View recent transaction logs.
- `--code <code>`: Filter history by stock code.
- `--n N`: Number of transaction records to display (default: 20).
```bash
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/history.py --code 600519 --n 5
```
