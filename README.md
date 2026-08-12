# mmtickerlab — A-Share Trading Assistant Skills

A collection of Claude Code skills for analyzing the Chinese A-share market and running paper trading simulations. All data is sourced via [akshare](https://github.com/akfamily/akshare).

## Project Structure

```
mmtickerlab/
├── README.md
├── AGENTS.md                          # Project conventions & workflow
├── skills.json                        # Claude Code skill registration
├── pyproject.toml                     # Python root deps (akshare, pandas)
├── uv.lock
├── data/                              # Root runtime data (gitignored)
│   ├── watchlist.json                 # User-managed stock watchlist
│   ├── stock_names.json               # Auto-generated name cache
│   └── cache.db                       # Root-level cache
└── skills/
    ├── market/                        # Market data & analysis skill
    │   ├── SKILL.md                   # Usage reference for Claude
    │   ├── requirements.txt           # Skill-specific deps
    │   ├── scripts/
    │   │   ├── akshare_patch.py       # TLS impersonation (curl_cffi) + retry
    │   │   ├── cache_db.py           # SQLite caching with trading-session TTL
    │   │   ├── overview.py           # Market overview (indices + breadth)
    │   │   ├── ranking.py            # Top gainers / losers
    │   │   ├── limit_up.py           # Limit-up pool
    │   │   ├── fund_flow.py          # Concept/Industry/BigDeal cash flow
    │   │   ├── stock_profile.py      # Deep-dive: realtime/kline/cyq/comment/
    │   │   │                         #   fundflow/financials/technical
    │   │   ├── indicators.py         # 20+ technical indicators
    │   │   ├── news.py               # Stock news
    │   │   └── save_review.py        # Save market review
    │   ├── references/
    │   │   └── scenarios.md          # Pre-market/Noon/Evening workflows
    │   └── data/                     # Market cache DB (gitignored)
    │
    └── sim-trade/                    # A-share simulation trading skill
        ├── SKILL.md                  # Usage reference for Claude
        ├── requirements.txt          # Skill-specific deps
        ├── scripts/
        │   ├── simtrade.py           # Unified account/order/portfolio/audit CLI
        │   ├── akshare_patch.py      # Retry + East Money TLS handling
        │   └── simtrade_core/        # Data gate, SQLite ledger, rules, matching
        ├── references/
        │   ├── data_contract.md      # Required quote/calendar evidence
        │   ├── trading_rules.md      # Versioned market and fee rules
        │   └── command_reference.md  # Commands and order statuses
        ├── tests/                    # Isolated database and live read-only tests
        └── data/                     # Simulation data (gitignored)
            └── simulation.db         # Accounts, orders, fills, lots and ledgers
```

## Setup

This project uses **uv** for Python dependency management. Each skill manages its own virtualenv and dependencies.

```bash
# Init market skill venv
uv venv skills/market/.venv
uv pip install --python skills/market/.venv -r skills/market/requirements.txt

# Init sim-trade skill venv
uv venv skills/sim-trade/.venv
uv pip install --python skills/sim-trade/.venv -r skills/sim-trade/requirements.txt
```

## Register Skills with Claude Code

Add this project's `skills.json` to your Claude Code config:

```json
{
  "inherits": [
    { "path": "/path/to/mmtickerlab/skills.json" }
  ]
}
```

## Available Tools

### 行情数据 (Market Data)
| Tool | Script | akshare API |
|---|---|---|
| K线数据 | `stock_profile.py --mode kline` | `stock_zh_a_hist()`, `stock_zh_a_hist_min_em()` |
| 实时行情-东财 | `stock_profile.py --mode realtime --source eastmoney` | `stock_zh_a_spot_em()` |
| 实时行情-新浪 | `stock_profile.py --mode realtime --source sina` | Direct Sina API / `stock_zh_a_spot()` |
| 实时行情-雪球 | `stock_profile.py --mode realtime --source xueqiu` | `stock_individual_spot_xq()` |
| 财务报表 | `stock_profile.py --mode financials` | `stock_*_sheet_by_report_em()` (×3) |
| 新闻资讯 | `news.py` | `stock_news_em()` |

### 技术分析 (Technical Analysis)
| Tool | Script | Details |
|---|---|---|
| 技术指标 | `stock_profile.py --mode technical` | 20+ indicators: SMA/EMA/MACD/RSI/KDJ/BOLL/ATR/CCI/WR/VWMA/MFI |
| 筹码分布 | `stock_profile.py --mode cyq` | `stock_cyq_em()` |

### 市场分析 (Market Analysis)
| Tool | Script | akshare API |
|---|---|---|
| 涨停股票 | `limit_up.py` | `stock_zt_pool_em()` |
| 千股千评(评分) | `stock_profile.py --mode comment` | `stock_comment_detail_zhpj_lspf_em()` |
| 关注指数 | (同上) | `stock_comment_detail_scrd_focus_em()` |
| 参与意愿 | (同上) | `stock_comment_detail_scrd_desire_em()` |
| 机构参与度 | (同上) | `stock_comment_detail_zlkp_jgcyd_em()` |

### 资金流向 (Fund Flow)
| Tool | Script | akshare API |
|---|---|---|
| 个股资金流 | `stock_profile.py --mode fundflow` | `stock_fund_flow_individual()` |
| 概念板块资金流 | `fund_flow.py --type concept` | `stock_fund_flow_concept()` |
| 行业板块资金流 | `fund_flow.py --type industry` | `stock_fund_flow_industry()` |
| 大单追踪 | `fund_flow.py --type bigdeal` | `stock_fund_flow_big_deal()` |

### 模拟交易 (Simulation Trading)
| Tool | Command | Rules |
|---|---|---|
| 数据健康检查 | `simtrade.py doctor --code 600519` | Calendar, quote contract, matching readiness |
| 创建账户 | `simtrade.py account create --name NAME --cash 500000` | Append-only opening ledger |
| 限价买卖 | `simtrade.py order buy\|sell CODE SHARES --price PRICE` | Strict session/data gates, visible-book fills |
| 订单管理 | `simtrade.py order list\|show\|cancel\|process` | Partial fills, cancellation, DAY expiry |
| 持仓和历史 | `simtrade.py portfolio`, `simtrade.py history` | T+1 lots, explicit unavailable valuations |
| 账本审计 | `simtrade.py audit` | Cash, freezes, fills and position invariants |

## East Money TLS Note

The market and sim-trade skills route known East Money calls through `curl_cffi` with retries. If queries hang, verify the relevant skill-local environment contains `curl_cffi` and inspect provider diagnostics.

## Key Rules (Sim-Trade)

- **Data gate**: No complete, fresh quote and confirmed trading day means no order or fill
- **T+1**: Purchased lots become sellable on the next confirmed trading day
- **Matching**: Limit orders consume only visible five-level liquidity and may remain open or partially filled
- **Lot/tick**: Buy multiples of 100, constrained odd-lot liquidation, ¥0.01 tick
- **Hours**: Confirmed trading days, 09:30–11:30 and 13:00–15:00; no bypass
- **Fees**: Configurable commission + 0.001% transfer fee both sides + 0.05% sell stamp tax
- **Storage**: Transactional SQLite ledger; no JSON/CSV reset or compatibility path
