---
title: "首板隔夜决策报告 — {{date}}"
date: "{{date}}"
category: "strategy"
market_regime: "{{market_regime}}"
decision: "{{decision}}"
veto_status: "{{veto_status}}"
summary: "{{summary}}"
---

# 🏳️ 首板隔夜决策报告 — {{date}}

- **交易日期 (as_of)**：{{date}} {{phase}}
- **策略环境定级 (market_regime)**：{{market_regime}}
- **核心策略决策 (decision)**：{{decision}}
- **执行状态 (status)**：{{status}}

---

## 1. 市场赚钱效应与环境门禁

- **今日首板总数**：{{first_board_count}} 家
- **昨日首板今日表现**：高开率 {{yesterday_first_board_up_pct}}%，平开率 {{yesterday_first_board_flat_pct}}%，低开率 {{yesterday_first_board_down_pct}}%
- **涨停封板质量**：全天炸板率 {{broken_board_ratio}}%（{{broken_count}} 家炸板 / {{limit_up_count}} 家涨停）
- **连板梯队高度**：最高板为 {{max_board_height}} 板，晋级成功率 {{promotion_rate}}%
- **环境门禁裁决**：{{environment_gate_result}}

---

## 2. 候选标的决策清单

| 标的代码 | 标的名称 | 所属题材 | 决策建议 | 核心证据 | 反证与失效条件 | 建议仓位上限 | 止损/退出计划 |
|:---|:---|:---|:---:|:---|:---|:---:|:---|
{{candidate_rows}}

---

## 3. 明日催化线索与外盘截面

- **隔夜外盘预期**：{{overnight_expectation}}
- **盘后重大公告**：{{post_market_announcements}}
- **明日宏观/经济数据窗口**：{{macro_schedule}}

---

## 4. 独立风控与仓位核算 (Risk Guard)

- **Regime 仓位乘数**：{{regime_multiplier}}
- **单票风险上限**：不超过账户总资产的 {{single_max_position}}%
- **账户最大亏损控制**：若首板出现极端负反馈，单日回撤上限锁定为 {{account_stop_loss}}%

---

## 5. 未知项与数据声明 (Unknowns)

- **缺失或未审计字段**：{{unknown_fields}}
- **模拟执行状态**：{{execution_status}}
