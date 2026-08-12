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
skills/market/.venv/bin/python skills/market/scripts/overview.py
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/portfolio.py
```

## Critical import order

**`akshare_patch` must be imported before `akshare.akshare` in every script.** The patch monkeypatches `requests.get` and `akshare.utils.func.request_with_retry` to add retry + User-Agent headers, and (market only) `curl_cffi` TLS impersonation for East Money domains. If `akshare` is imported first, the patches will not take effect on already-loaded submodules.

## Cache system

Each skill has its own `cache_db.py` in `scripts/` that stores data in a skill-local SQLite DB (`skills/<skill>/data/cache.db`). Cache TTLs are tied to A-share trading sessions (outside trading hours, entries expire at the *next* session's 09:15 open). The DB is auto-created on first use.

## Data locations

- **Root `data/`**: `watchlist.json` (editable list of stock codes to track), `stock_names.json` (global name lookup cache)
- **Market data**: `skills/market/data/` (cache.db, saved reviews)
- **Sim-Trade data**: `skills/sim-trade/data/simulation/` (portfolio.json, history.csv)
- Working directory is the project root (where this file lives).

## Simulation trading rules (sim-trade)

- **T+1**: `available_shares` = 0 on purchase day, synced to `shares` when portfolio crosses a calendar date boundary.
- **Lot size**: Buys must be multiples of 100; sells allow any amount up to available.
- **Price limits**: ±10% (normal), ±5% (ST), ±20% (ChiNext 30xxxx / Star 68xxxx), ±30% (Beijing 4xxxxx/8xxxxx)
- **Trading hours enforced** (9:30–11:30, 13:00–15:00 weekdays); bypass with `--force`
- **Fees**: 0.025% commission (min ¥5) + 0.002% transfer fee both sides; 0.1% stamp tax on sell only
- Reset with `sim-trade/scripts/reset.py` before first use

## Plan & Review skill (plan-review)

- **Purpose**: Strict pre-market, intraday, and post-market research reports backed by validated AKShare snapshots
- **Workflow**: `skills/plan-review/scripts/workflow.py` (`capture`, `prepare`, `validate`)
- **Bundles**: `skills/plan-review/data/YYYYMMDD/{pre,noon,post}_bundle.json`
- **Reports**: `report/YYYYMMDD_{盘前计划,盘中复盘,盘后复盘}.md`
- **Hard gate**: a missing, stale, incomplete, or schema-invalid required dataset blocks report creation
- **No external deps in workflow**: it calls `skills/market/scripts/report_data.py` through the market venv

This is a read-only process layer over `market` data. See `skills/plan-review/SKILL.md` for the full workflow.
## East Money TLS blocking (market only)

East Money APIs can block Python's default `requests` TLS fingerprint. The market skill's `akshare_patch.py` routes known East Money domains through plain `curl_cffi` with retry logic; current endpoint tests show browser impersonation causes connection drops. If an endpoint hangs, verify `curl_cffi` is installed and inspect the retry diagnostics.
