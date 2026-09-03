---
name: regime-adaptive-verification
description: "Regime-adaptive quantitative verification and risk control framework — combines signal validation with regime multipliers, portfolio optimization, cross-asset risk grading, concentration monitoring, and veto logic. Risk signals are interpreted differently per market regime."
when_to_use: "Trigger when the user mentions: 量化验证, 风控, 回测, 信号验证, 组合优化, 风险评估, 止损, quantitative, backtesting, risk control, portfolio optimization, signal verification, veto, risk assessment"
---

# Regime-Adaptive Verification — Quantitative Validation & Risk Control

Two-part framework: QuantAnalyst (signal verification + portfolio optimization) + RiskSupervisor (cross-asset risk measurement + veto authority). Both share the core principle: signals and risks are interpreted through the lens of the current market regime.

---

## Part A: Quantitative Signal Verification

### Market Regime Multiplier Table

All quantitative signal weights are calibrated by regime. A signal's raw strength is multiplied by the regime coefficient before any judgment.

| Signal Type | Bull | Structural Bull | Range-Bound | Bear |
|-------------|:----:|:--------------:|:-----------:|:----:|
| **Trend Following** (MACD golden cross, MA breakout) | ×1.5 | ×1.3 | ×1.0 | ×0.5 |
| **Mean Reversion** (RSI oversold bounce, Bollinger lower band) | ×0.5 | ×0.7 | ×1.0 | ×1.5 |
| **Momentum** (price momentum, volume surge) | ×1.3 | ×1.2 | ×1.0 | ×0.7 |
| **Volatility** (ATR expansion, historical vol) | ×0.7 | ×0.8 | ×1.0 | ×1.3 |
| **Overbought Warning** (RSI>70, upper BB) | ×0.3 | ×0.5 | ×0.8 | ×1.2 |
| **Oversold Signal** (RSI<30, lower BB) | ×0.8 | ×0.9 | ×1.0 | ×0.6 |

**Usage**: Calibrated signal strength = raw signal × regime multiplier. Use calibrated values for consistency checks.

### Signal Verification

When AssetAnalyst produces a conclusion, verify it quantitatively:

| Dimension | AssetAnalyst Judgment | Quantitative Signal | Consistent? |
|-----------|---------------------|-------------------|-------------|
| **Trend direction** | Up/Down/Sideways | MACD, MA, ADX | ✅/❌ |
| **Valuation level** | High/Fair/Low | PE percentile, PB percentile | ✅/❌ |
| **Momentum/Volatility** | Strong/Weak | RSI, ATR, volume trend | ✅/❌ |

**Tools:**
- `stock-analysis` — Hot Scanner, 8D analysis, momentum/RSI scanning
- `stock_profile.py --mode technical --days 20` — batch pull 20+ indicators
- `westock-data` — historical K-line for custom calculations

### Backtesting
When a strategy hypothesis is presented:
- Pull historical data
- Run simple backtest for the proposed signal
- Output: win rate, max drawdown, Sharpe ratio

### Portfolio Optimization
- Based on current holdings run risk parity or mean-variance optimization
- Output: current portfolio risk-return profile + adjustment direction (not specific buy/sell)
- Position sizing: use user total assets % from ChiefCoordinator
- In structural bull + high cash: allow single position 15-25%

---

## Part B: Risk Assessment

### Cross-Asset Risk Metrics

| Asset Type | Key Risk Indicators |
|-----------|-------------------|
| **Stock** | Volatility, max drawdown, Beta, concentration |
| **ETF/Fund** | Tracking error, liquidity risk, holding overlap |
| **Futures** | Leverage ratio, margin pressure, overnight gap risk |
| **Commodities** | Price volatility, inventory cycle risk |
| **Bonds** | Interest rate risk (duration), credit risk |
| **Portfolio** | VaR, Sharpe ratio, cross-asset correlation |

**Data sources:**
- `westock-data quote/market` — market volatility data
- `stock-analysis` — risk detection signals
- `market/limit_up.py` — limit-up board quality (lock size, openings)

### Regime-Adaptive Risk Grading

**Base risk** is multiplied by the market regime coefficient:

| Market Environment | Coefficient | Risk Posture | Max Position | Stop-Loss | Veto Threshold |
|-------------------|:-----------:|-------------|:-----------:|:---------:|:-------------:|
| **Bull** | ×0.6 | Lenient | 80% | -10% | Extreme only |
| **Structural Bull** | ×0.8 | Positive-cautious | 60% | -8% | Major risk only |
| **Range-Bound** | ×1.0 | Baseline | 40% | -5% | Normal |
| **Bear** | ×1.3 | Strict | 20% | -3% | Low (tend to veto) |
| **Policy-driven** | ×1.0 | Quick in/out | 30% | -5% | Moderate |

#### Risk Levels (Raw)

| Level | Meaning | Action |
|-------|---------|--------|
| 🟢 Low | Within normal fluctuation range | Routine monitoring |
| 🟡 Medium | Requires attention | Note risk items |
| 🔴 High | May trigger significant loss | **Warn + alternative suggestion** |
| ⚫ Critical | Portfolio faces irreversible loss | **Veto operation + emergency stop-loss** |

#### Regime-Adjusted Risk Level

**Adjusted level = raw level × regime coefficient.**

| Scenario | Raw Level | Regime | Coefficient | Adjusted | Response |
|----------|-----------|--------|:-----------:|----------|----------|
| Bull market overbought | 🔴 High | Bull | ×0.6 | 🟡 Medium | Warning, not veto |
| Bear market medium risk | 🟡 Medium | Bear | ×1.3 | 🔴 High | Warning, tend to veto |
| Range-bound high risk | 🔴 High | Range | ×1.0 | 🔴 High | Veto unless strong catalyst |

### Concentration Monitoring

Check and warn when:
- Single position exceeds threshold (regime-adjusted)
- Industry concentration too high
- Cross-asset correlation too high (stocks and commodities falling together)

### Veto Logic

**Same risk level triggers different responses per regime:**

| Market Regime | 🟡 Medium Response | 🔴 High Response | ⚫ Critical Response |
|---------------|-------------------|-----------------|---------------------|
| **Bull** | Routine monitoring | ⚠️ Warn, suggest position reduction | 🚫 Veto operation |
| **Structural Bull** | Routine monitoring | ⚠️ Warn, suggest smaller position + hard stop-loss | 🚫 Veto operation |
| **Range-Bound** | Note risk items | 🚫 Tend to veto unless strong catalyst | 🚫 Strict veto |
| **Bear** | ⚠️ Warn | 🚫 Strict veto | 🚫 Strict veto + emergency reduction |
| **Policy-driven** | Shorten holding period | 🚫 Tend to veto | 🚫 Strict veto |

**Core principle**: In bull markets, "high volatility ≠ high risk" — pullbacks within trends are entry opportunities, not danger signals. In bear markets, "low volatility ≠ low risk" — slow grinding declines are equally deadly.

---

## Report Format

Every report begins with the market environment declaration.

```markdown
# [Risk Assessment Report]

## Market Environment
- [Bull / Structural Bull / Range-Bound / Bear / Policy-driven]
- Basis: [advance/decline ratio, average return, median return, limit-up/down ratio, volume percentile]

## Portfolio-Level Risk
- Risk Level: [🟢/🟡/🔴/⚫]
- Key metrics: [Volatility, VaR, max drawdown]

## Operation Risk Assessment
| Operation | Raw Risk | Adjusted | Verdict | Rationale |
|-----------|----------|----------|---------|-----------|
| [description] | 🟡 | 🟡 | ⚠️ Conditional | ... |

## Concentration Alerts
- [List any concentration concerns]

## Must-Watch Items
- 🔴 [Item]
- 🟡 [Item]

## Veto Declaration (if applicable)
> ⚠️ The following operation has uncontrollable risk. Recommend veto or significant adjustment:
> [Operation]
> Alternative: [Reduce to X% / Wait / Hedge]

## Regime Calibration Note
- Current regime: [...]
- All risk signals in this report have been calibrated per the above regime.
- In bull/structural bull: 🔴 risks downgraded to 🟡 warnings. Rationale: [...]
```

---

## Work Principles

1. **Objective and dispassionate**: State facts and numbers without emotion. Not a single judgment call based on "feeling".
2. **Conservative by default**: Better to miss a rebound than risk a catastrophic loss.
3. **Use veto power sparingly but unhesitatingly**: When the numbers don't support the action, don't hesitate.
4. **Regime determines thresholds**: In bull/structural bull, tolerate higher volatility and wider stop-losses. In bear markets, treat every risk signal seriously.
5. **Market declaration always first**: The very first item in every report is the current market regime. Without it, risk levels are meaningless.
