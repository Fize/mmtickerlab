---
name: intelligence-gathering
description: "Cross-asset intelligence collection methodology — covers stocks, ETFs/funds, futures, commodities, bonds, and macro. Multi-channel collection, intelligence classification (asset/region/impact/importance), and structured briefing output. Reports facts only, no analysis."
when_to_use: "Trigger when the user mentions: 情报, 新闻, 消息面, 资金流向, 涨停板, intelligence, news gathering, market news, fund flow, briefing"
---

# Intelligence Gathering — Multi-Channel Collection & Classification

The team's intelligence infrastructure. All downstream analysis (AssetAnalyst, QuantAnalyst, RiskSupervisor) feeds on this output. Provide only WHAT happened, never WHAT IT MEANS or WHAT TO DO.

---

## Coverage Scope

All asset classes:
| Asset Class | Examples |
|-------------|----------|
| **Stocks** | Individual equities, A-shares, HK, US markets |
| **ETFs / Funds** | Index ETFs, sector funds, mutual funds, money market |
| **Futures** | Commodity futures, index futures, treasury futures |
| **Commodities** | Gold, crude oil, copper, agricultural products |
| **Bonds** | Government bonds, corporate bonds, convertible bonds |
| **Macro** | GDP, CPI, PMI, interest rates, policy, geopolitics |

---

## Collection Channels

### Primary: Tencent News API
Use `tencent-news` skill as the primary engine. Pull financial news, policy releases, macro data releases, and industry dynamics.

**Call pattern**: Search by keyword or broad topic. For broad market scanning, use hot topics lists.

### Secondary: Agent-Browser
Use for supplementary sources that APIs don't cover:
- Central bank websites (PBOC, Federal Reserve, ECB)
- National statistics bureau
- Exchange announcements (Shanghai, Shenzhen, HKEX)
- Industry-specific media

### Focused Collection: Market Scripts
When the task targets a specific stock or ETF, use `market` skill scripts for precise intelligence:

| Scenario | Command | Purpose |
|----------|---------|---------|
| **Stock news** | `news.py <code> --n 5` | Get the latest 5 news items for a specific stock — more focused than broad search |
| **Sector fund flow** | `fund_flow.py --type industry --period 5` | 5-day sector-level capital flow data |
| **Concept fund flow** | `fund_flow.py --type concept --period 1` | 1-day concept-level capital flow (short-term sentiment) |
| **Limit-up analysis** | `limit_up.py` | Limit-up board details (lock time, order size, openings) |

**Principle**: Use Tencent News for broad scanning, use market scripts for asset-level focus. They complement, not replace each other.

---

## Intelligence Classification

Every piece of intelligence must be tagged with:

| Dimension | Options |
|-----------|---------|
| **Asset class** | Stock / Fund / Futures / Commodity / Bond / Macro |
| **Region** | China / US / Europe / Asia-Pacific / Global |
| **Impact direction** | Positive / Negative / Neutral |
| **Importance** | 🔴 High (directly affects position decisions) / 🟡 Medium (worth attention) / 🔵 Low (informational) |

---

## Output Format: Intelligence Briefing (情报快报)

All collected intelligence must be consolidated into a structured briefing.

```markdown
# [Intelligence Briefing] YYYY-MM-DD

## 🔴 High Importance
| Time | Asset / Region | Summary | Source | Direction |
|------|---------------|---------|--------|-----------|
| HH:MM | Stock/China | [concise summary of event] | tencent-news | Positive |

## 🟡 Medium Importance
| Time | Asset / Region | Summary | Source | Direction |
|------|---------------|---------|--------|-----------|
| HH:MM | Macro/US | [concise summary of event] | agent-browser | Neutral |

## 🔵 Low Importance
| Time | Asset / Region | Summary | Source | Direction |
|------|---------------|---------|--------|-----------|
| HH:MM | Commodity/Global | [concise summary of event] | tencent-news | Negative |

## Key Data Releases
- [List any CPI/GDP/PMI/interest rate decisions / employment data released today]
```

### Format Rules
- One row per intelligence item — concise, single-line summaries
- Do NOT filter out "unimportant" items — let downstream consumers decide
- Always include source attribution
- Always include time of event (not time of collection)

---

## Collection Workflow

1. **Receive task** from ChiefCoordinator — contains asset type, target, scope
2. **Scan** — use Tencent News for broad intelligence sweep
3. **Focus** — if specific asset, run market scripts for targeted collection
4. **Classify** — tag every item by asset class, region, direction, importance
5. **Compile** — structure into Intelligence Briefing format
6. **Deliver** — pass structured briefing to downstream analysts

---

## Boundaries (STRICT)

| ✅ Allowed | ❌ Not Allowed |
|-----------|---------------|
| Facts, data, sources, timestamps | Analysis, predictions, or recommendations |
| Labels and classifications | "This means prices will go up" |
| Concise summaries with attribution | Filtering items as "unimportant" for the consumer |
| Source links and references | Valuation judgments or investment advice |

**Core principle**: The intelligence brief is raw material. Analysis is someone else's job. If there's any doubt whether something is analysis or fact, label it as analysis and let the consumer decide.

## Tool Integration Summary

| Tool | When to Use |
|------|-------------|
| `tencent-news` | Primary — broad financial news, policy, macro data |
| `agent-browser` | Supplementary — official sources, exchange filings, industry media |
| `market/news.py` | Stock-specific focused news |
| `market/fund_flow.py` | Sector/concept capital flow data |
| `market/limit_up.py` | Limit-up board analysis |
