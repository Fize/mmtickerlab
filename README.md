# ChoseStock — A-Share Trading Assistant Skills

ChoseStock is a collection of Claude Code skills for analyzing the Chinese A-share market and running paper trading simulations. All data is sourced via [akshare](https://github.com/akfamily/akshare).

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
        │   ├── akshare_patch.py      # Retry + User-Agent patching
        │   ├── cache_db.py           # SQLite caching
        │   ├── reset.py              # Account initialization
        │   ├── portfolio.py          # Holdings, P&L, market value
        │   ├── buy.py                # Buy order (T+1, lot size, price limits)
        │   ├── sell.py               # Sell order (T+1, fees, stamp tax)
        │   └── history.py            # Transaction history
        ├── references/
        │   └── portfolio_schema.md   # Portfolio JSON schema
        └── data/                     # Simulation data (gitignored)
            └── simulation/
                ├── portfolio.json    # Account state
                └── history.csv       # Order history
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

## Available Tools (17 total)

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
| Tool | Script | Rules |
|---|---|---|
| 初始化账户 | `reset.py --cash 500000` | Sets initial capital, T+1 sync |
| 买入 | `buy.py <code> <qty>` | Multiples of 100, price limit check, fees |
| 卖出 | `sell.py <code> <qty>` | T+1 available check, stamp tax 0.1% |
| 持仓查询 | `portfolio.py` | Real-time market value & P&L |
| 交易历史 | `history.py --code 600519` | Filterable order log |

## East Money TLS Note

The market skill patches East Money API calls through `curl_cffi` with Chrome 120 TLS impersonation (`akshare_patch.py`). If queries hang on East Money endpoints, verify `curl_cffi` is installed in the market venv.

## Key Rules (Sim-Trade)

- **T+1**: Purchased shares available for sale starting next calendar day
- **Lot**: Buy multiples of 100; sell any amount
- **Limits**: ±10% (normal), ±5% (ST), ±20% (ChiNext/Star), ±30% (Beijing)
- **Hours**: Weekdays 9:30–11:30, 13:00–15:00 (`--force` to bypass)
- **Fees**: 0.025% commission (min ¥5) + 0.002% transfer fee (both sides); 0.1% stamp tax (sell only)
