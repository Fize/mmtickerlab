# Portfolio & History Data Schemas

The simulation account persists its state in two files inside `data/simulation/`:
1. `portfolio.json`: Holds cash, account details, and active holdings.
2. `history.csv`: Records transaction logs.

---

## 1. Portfolio Schema (`data/simulation/portfolio.json`)

```json
{
  "account_name": "我的模拟账户",
  "cash": 500000.0,
  "frozen_cash": 0.0,
  "positions": {
    "600519": {
      "name": "贵州茅台",
      "shares": 100,
      "available_shares": 0,
      "buy_date": "2026-06-18",
      "cost_per_share": 1456.00,
      "total_cost": 145600.0
    }
  },
  "created_at": "2026-06-18",
  "updated_at": "2026-06-18T10:30:00"
}
```

### Property Reference

- `account_name`: String identifier for the portfolio.
- `cash`: Float representing available liquid cash (Yuan).
- `frozen_cash`: Float representing cash held for pending orders (reserved for limit order features).
- `positions`: Dictionary of active stock holdings, keyed by 6-digit stock codes.
  - `name`: Stock short name in Chinese.
  - `shares`: Total number of shares currently held.
  - `available_shares`: Current sellable shares (computed dynamically to enforce T+1).
  - `buy_date`: The date of the most recent purchase (`YYYY-MM-DD`).
  - `cost_per_share`: Weighted average buy price per share.
  - `total_cost`: Total capital invested in this position.
- `created_at`: Creation date of the account (`YYYY-MM-DD`).
- `updated_at`: Last modification ISO timestamp.

---

## 2. History Schema (`data/simulation/history.csv`)

Transactions are appended to `data/simulation/history.csv`.

### Columns

- `timestamp`: Date and time of order execution (`YYYY-MM-DD HH:MM:SS`).
- `code`: 6-digit stock code (e.g., `600519`).
- `name`: Stock short name (e.g., `贵州茅台`).
- `action`: `BUY` or `SELL`.
- `price`: Execution price per share (Yuan).
- `qty`: Share quantity.
- `amount`: Core trade value (`price * qty`).
- `commission`: Charged commission (0.025%, min ¥5).
- `stamp_tax`: Charged stamp tax (0.1%, sell only).
- `transfer_fee`: Charged transfer fee (0.002%).
- `total_cost`: Total transaction cost (Cash deducted for buys, or net cash received for sells).
