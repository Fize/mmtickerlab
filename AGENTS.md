# AGENTS.md — mmtickerlab (A-Share Trading Assistant)

## Project nature

This is **not a package or application**. It is a collection of Claude Code skills (market data & paper trading) that run Python scripts via `uv`. `pyproject.toml` sets `package = false`.

## Dependency management

- Use `uv`, never `pip` directly.
- Each skill has its **own** virtualenv and `requirements.txt`:
  - `skills/market/.venv` / `skills/market/requirements.txt`
  - `skills/sim-trade/.venv` / `skills/sim-trade/requirements.txt`
- To init a fresh venv: `uv venv skills/<skill>/.venv` then `uv pip install --python skills/<skill>/.venv -r skills/<skill>/requirements.txt`
- The root `pyproject.toml` declares `akshare` + `pandas` but the skills manage their own deps independently.

## How to run scripts

All scripts run from the **project root** with the skill's own python:

```bash
skills/market/.venv/bin/python skills/market/scripts/market_data.py snapshot --date YYYYMMDD --session close
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/simtrade.py portfolio
```

## Critical import order

**`akshare_patch` must be imported before `akshare.akshare` in every data-provider module.** The patch monkeypatches `requests.get` and `akshare.utils.func.request_with_retry` to add retries, headers, and `curl_cffi` handling for East Money domains. If `akshare` is imported first, patches may not affect already-loaded submodules.

## Cache system

The market skill uses `skills/market/scripts/cache_db.py` and `skills/market/data/cache.db`. Cache TTLs are tied to A-share trading sessions. Sim-trade does not share this cache; it stores its auditable state and captured quote snapshots in its own SQLite database.

## Data locations

- **Root `data/`**: `watchlist.json` (editable list of stock codes to track), `stock_names.json` (global name lookup cache)
- **Market data**: `skills/market/data/` (cache.db, saved reviews)
- **Sim-Trade data**: `skills/sim-trade/data/simulation.db` (accounts, orders, fills, lots, cash ledger, quote snapshots, trading calendar)
- Working directory is the project root (where this file lives).

## Simulation trading rules (sim-trade)

- Single CLI: `skills/sim-trade/scripts/simtrade.py`; removed scripts and JSON/CSV formats are not supported.
- **Hard data gate**: matching requires a fresh same-day identity, timestamp, last/pre-close, provider limits, listing date, trading state, and executable five-level book. There is no `--force`.
- **Orders**: limit orders only, visible-book partial fills, DAY expiry, cancellation, and persistent order/fill IDs.
- **T+1**: bought lots unlock on the next confirmed trading day from the AKShare calendar.
- **Lot/tick**: buys are multiples of 100; sells are multiples of 100 unless liquidating all free odd shares; price tick is ¥0.01.
- **Fees**: configurable commission (default 0.025%, min ¥5), 0.001% transfer fee both sides, and 0.05% sell stamp tax; all calculations use decimal/fen arithmetic.
- Create accounts with `simtrade.py account create`; archive them rather than resetting or deleting the ledger.

## Plan & Review skill (plan-review)

- **Purpose**: Strict pre-market, intraday, and post-market research reports backed by validated AKShare snapshots
- **Workflow**: `skills/plan-review/scripts/workflow.py` (`capture`, `prepare`, `validate`); capture `close` after 15:05 and `lhb` separately after 16:30
- **Bundles**: `skills/plan-review/data/YYYYMMDD/{pre,noon,post}_bundle.json`
- **Reports**: `report/YYYYMMDD_{盘前计划,盘中复盘,盘后复盘}.md`
- **Hard gate**: a missing, stale, incomplete, or schema-invalid required dataset blocks report creation
- **No external deps in workflow**: it calls `skills/market/scripts/market_data.py` through the market venv

This is a read-only process layer over `market` data. See `skills/plan-review/SKILL.md` for the full workflow.
## East Money TLS blocking (market only)

East Money APIs can block Python's default `requests` TLS fingerprint. The market skill's `akshare_patch.py` routes known East Money domains through plain `curl_cffi` with retry logic; current endpoint tests show browser impersonation causes connection drops. If an endpoint hangs, verify `curl_cffi` is installed and inspect the retry diagnostics.
