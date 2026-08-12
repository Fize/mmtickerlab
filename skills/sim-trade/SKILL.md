---
name: sim-trade
description: Reliable A-share paper-trading system backed by strict live-market data checks and an auditable SQLite ledger. Use when Codex needs to create or inspect a simulated account, place/cancel/process Shanghai, Shenzhen, or Beijing A-share limit orders, enforce trading sessions and T+1 settlement, inspect positions/P&L/history, audit balances, or diagnose whether AKShare data is sufficient for safe simulation. A股模拟交易系统，适用于严格行情门禁、限价委托、部分成交、T+1、持仓盈亏、交易流水和账本审计。
---

# Sim Trade

Operate the deterministic CLI from the repository root. Never invent a quote, bypass a failed data check, or substitute cost for market value.

## Set up

Create the skill-local environment only when it is missing:

```bash
uv venv skills/sim-trade/.venv
uv pip install --python skills/sim-trade/.venv -r skills/sim-trade/requirements.txt
```

Set the command prefix:

```bash
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/simtrade.py
```

Use `--json` before the command when machine-readable output is required. Use `--db PATH` only for an explicitly requested alternate account database or isolated testing.

## Follow the workflow

1. Run `doctor --code CODE` before the first live-data operation of a session.
2. Stop if `doctor` reports a failed required check. Do not place an order from partial or stale data.
3. Create an account with `account create --name NAME --cash AMOUNT`. Do not reset or overwrite an account.
4. Inspect a security with `quote CODE` before discussing a possible order.
5. Submit only explicit limit orders with `order buy|sell CODE SHARES --price PRICE`.
6. Report the returned order status exactly. `OPEN` and `PARTIALLY_FILLED` are not completed trades.
7. Use `order process [--order-id ID]` during a trading session to retry open DAY orders against a new qualified order-book snapshot.
8. Use `order cancel ID` to release an open order's frozen cash or shares.
9. Use `portfolio`, `history`, and `audit` for review. If valuation is unavailable, preserve that state instead of calculating a substitute value.

## Observe hard gates

- Support only six-digit Shanghai, Shenzhen, and Beijing A-share stock codes recognized by the CLI.
- Support limit orders only. Do not simulate market orders or fabricate fills.
- Reject order placement outside an official trading day and the continuous-auction sessions 09:30–11:30 and 13:00–15:00 Asia/Shanghai.
- Require a same-day, fresh, complete quote for matching: security identity, quote timestamp, last/pre-close, explicit upper/lower limits, listing date, and at least one side of the five-level book.
- Leave an order open when its limit does not cross the visible book or visible quantity is insufficient.
- Enforce next-trading-day availability for bought shares. Do not use calendar-day rollover.
- Never expose or recreate the removed JSON/CSV account format, old single-action scripts, `reset`, or `--force`.

Read [references/data_contract.md](references/data_contract.md) when diagnosing quote failures or changing a provider. Read [references/trading_rules.md](references/trading_rules.md) before changing trading, settlement, price-limit, odd-lot, or fee behavior. Read [references/command_reference.md](references/command_reference.md) for commands and statuses.
