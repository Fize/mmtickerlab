---
name: multi-asset-analysis
description: "Multi-asset analysis framework — integrated fundamental + technical analysis covering stocks, ETFs/funds, futures, commodities, and bonds. Includes regime-calibrated scoring (1-10) and tool integration guide for westock-data, hithink, and market scripts."
when_to_use: "Trigger when the user mentions: 分析, 基本面, 技术面, 估值, 股票分析, ETF分析, 期货, 债券, stock analysis, fundamental analysis, technical analysis, asset analysis, multi-asset"
---

# Multi-Asset Analysis — Fundamental + Technical Integrated Framework

Sole content producer for asset analysis. Covers stocks, ETFs/funds, futures, commodities, and bonds. Merged fundamental and technical analysis into a single role because a holistic judgment requires both simultaneously.

---

## Market Regime Calibration (Mandatory Read Before Each Analysis)

**Every analysis begins by obtaining the current market regime from ChiefCoordinator. The same technical signal means entirely different things under different regimes.**

| Market Regime | Technical Analysis Adjustment |
|---------------|------------------------------|
| **Bull Market** | RSI overbought / Bollinger upper band / KDJ high → downgrade significance. Bull markets sustain overbought conditions. Trend signals take priority. |
| **Structural Bull** | Technical overbought does not constitute a veto reason. Focus on fundamentals + sector logic. Overbought is tolerable. |
| **Range-Bound** | Technical signals at normal weight. Overbought = sell, oversold = buy. |
| **Bear Market** | All bullish signals downgraded. Oversold can continue to oversold. No bottom fishing. |

---

## Stock Analysis

### Fundamental Analysis
| Metric | What to Evaluate | Data Source |
|--------|------------------|-------------|
| **PE / PB** | Current vs historical range, vs industry avg | `westock-data finance` |
| **ROE** | Profitability and capital efficiency | `westock-data finance` |
| **Debt ratio** | Financial leverage and solvency risk | `westock-data finance` |
| **Free cash flow** | Cash generation quality and sustainability | `westock-data finance` |
| **Revenue growth** | Top-line momentum, YoY and QoQ | `westock-data finance` |
| **Profit quality** | Operating vs non-operating income | `westock-data finance` |
| **Moat assessment** | Competitive advantage durability | `westock-data rating` |

### Technical Analysis
Use `stock_profile.py --mode technical --days 20` to pull all indicators simultaneously (MACD, RSI, KDJ, BOLL, ATR, CCI, WR, VWMA, MFI, etc.):

| Group | Indicators | Purpose |
|-------|-----------|---------|
| **Trend** | Moving averages, MACD | Direction and strength |
| **Momentum** | RSI, KDJ, CCI, WR | Overbought/oversold |
| **Volatility** | BOLL, ATR | Expansion/contraction |
| **Volume** | VWMA, MFI | Money flow confirmation |

### Supplementary Market Scripts
| Data | Command | Purpose |
|------|---------|---------|
| **Chip cost distribution** | `stock_profile.py --mode cyq --days 5` | Concentration and key cost zones |
| **Institutional views** | `stock_profile.py --mode comment` | Research report summaries |
| **Capital flow** | `stock_profile.py --mode fundflow` | Large/small order flow |

### Regime-Calibrated Conclusion
"Overbought but tolerable in bull market" vs "Overbought — reduce exposure in range-bound market". Always annotate the regime adjustment.

---

## ETF / Fund Analysis

| Dimension | What to Evaluate |
|-----------|------------------|
| **Tracking index** | What index it follows, index composition, sector weighting |
| **Holdings structure** | Top holdings, concentration, sector allocation |
| **Fees** | Management fee, custody fee, total expense ratio |
| **Tracking error** | How closely it follows the index |
| **Size** | AUM, liquidity, bid-ask spread |
| **NAV trend** | Price trajectory, relative to index |
| **Alpha / Beta** | Risk-adjusted performance vs benchmark |

**Conclusion**: Is this fund suitable for the current market regime and portfolio needs?

---

## Futures Analysis

| Dimension | What to Evaluate |
|-----------|------------------|
| **Supply-demand** | Production data, inventory levels, consumption trends |
| **Basis** | Spot vs futures price relationship |
| **Seasonality** | Historical seasonal patterns |
| **Price trend** | Contract price trajectory, trend strength |
| **Volume & open interest** | Liquidity and participation |

**Conclusion**: Long/short direction for the current contract, with regime notes.

---

## Commodities Analysis (Gold / Oil / Copper)

| Dimension | What to Evaluate |
|-----------|------------------|
| **Global supply-demand** | Production, consumption, inventory, marginal cost |
| **Geopolitics** | Trade tensions, supply disruptions, sanctions |
| **USD impact** | Dollar correlation, interest rate linkage |
| **Price trend** | Trend direction, support/resistance levels |
| **Key levels** | Major technical zones |

**Conclusion**: Trend judgment + key price levels.

---

## Bond Analysis

| Dimension | What to Evaluate |
|-----------|------------------|
| **Rate environment** | Central bank policy rate trajectory, yield curve |
| **Credit rating** | Issuer credit quality, rating outlook |
| **Duration** | Interest rate sensitivity |
| **Yield** | Current yield, yield to maturity, spread vs risk-free |

**Conclusion**: Worth allocating or not, with rationale.

---

## Comprehensive Scoring System (1-10)

Each asset receives three scores, all regime-calibrated:

```markdown
## Comprehensive Scoring

| Dimension | Score (1-10) | Rationale | Regime Adjustment |
|-----------|-------------|-----------|-------------------|
| Fundamentals | X | Valuation, quality, moat | — |
| Technicals | X | Trend, momentum, volume | Adjusted per regime table |
| Overall | X | Weighted composite | Regime-annotated |
```

**Score interpretation:**
- 8-10: Strong buy, regime supports
- 6-7: Positive, reasonable risk/reward
- 4-5: Neutral, mixed signals
- 2-3: Cautious, regime-hashened
- 1: Avoid

---

## Tool Integration Guide

### Tool Chain Order
1. **westock-data** (primary): Financial data, valuation, K-line, consensus, ratings
2. **stock-analysis**: US/crypto 8D analysis, heatmap scanning
3. **market scripts** (complementary, not replacement):

| Scenario | Command | Replaces |
|----------|---------|----------|
| Technical indicators | `stock_profile.py --mode technical --days 20` | Manual app-by-app lookup |
| Chip cost distribution | `stock_profile.py --mode cyq --days 5` | Hithink doesn't have this — **mandatory** |
| Institutional comments | `stock_profile.py --mode comment` | Complements westock-data consensus |
| Capital flow | `stock_profile.py --mode fundflow` | Cross-validate with hithink |
| Stock news | `news.py <code> --n 5` | More focused than broad search |

### Complete Workflow
1. Pull fundamentals and pricing from `westock-data`
2. Pull technical indicators and chip data from `market` scripts
3. Pull institutional views and capital flow from `market` scripts
4. Cross-reference with `stock-analysis` for signal scanning
5. Merge all data into a single analysis report

---

## Output Format

```markdown
# [Multi-Asset Analysis] {Asset Name} ({Code}) — {Asset Type}

## 1. Core Conclusion
[Market regime: ...]
[One-line: current status + direction, including regime calibration note]

## 2. Fundamental Analysis
- Valuation level: [with context]
- Financial/operational quality: [ROE, debt, FCF summary]
- Industry position: [competitive standing]

## 3. Technical Analysis
- Trend: [Up/Down/Sideways] · Strength: [Strong/Medium/Weak]
- Key levels: Resistance [X] / Support [Y]
- Signal summary: [MACD/RSI/MA digest with regime adjustment]

## 4. Comprehensive Score
| Dimension | Score (1-10) | Note |
|-----------|-------------|------|
| Fundamental | X | ... |
| Technical | X | ... |
| Overall | X | ... |

## 5. Key Risks
- [Risk 1]
- [Risk 2]
```

## Boundaries

| ✅ Allowed | ❌ Not Allowed |
|-----------|---------------|
| Valuation range, trend judgment, key levels | Macroeconomic thesis (ChiefCoordinator's domain) |
| Signal intensity, asset ranking | Final buy/sell decisions (ChiefCoordinator's domain) |
| Position suggestions based on total asset % | Risk portfolio assessment (RiskSupervisor's domain) |
