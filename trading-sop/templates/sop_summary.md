---
title: "SOP 执行摘要 — {{chain_name}} ({{date}})"
date: "{{date}}"
category: "sop"
code: "{{code}}"
ticker_name: "{{ticker_name}}"
regime: "{{regime}}"
veto_status: "{{veto_status}}"
summary: "{{summary}}"
---

# 📋 SOP 执行摘要 — {{chain_name}} ({{date}})

> 执行链：`{{chain_name}}`  
> 标的代码：`{{code}}`（{{ticker_name}}）  
> 生成时间：{{generated_at}}

---

## 一、大势环境（Regime）
- **当前定性**：{{regime}}（来源：risk-guard）
- **仓位乘数基准**：{{position_multiplier}}

## 二、关键信息摘要
- **宏观 / 外盘**：{{macro_summary}}
- **市场结构**：{{structure_summary}}
- **标的研究**：{{ticker_summary}}

## 三、风控审查结论
- **门禁状态**：{{veto_status_badge}}
- **动态止损线**：{{stop_loss_price}} 元（若阻断则为“严禁开仓”）
- **仓位上限建议**：不超过账户总资产的 {{max_position_pct}}%

## 四、可操作建议
> 基于上述全链路分析，当前操作指引：

**{{action_headline}}**

{{action_details}}

- **失效条件**：{{invalidation_condition}}

## 五、数据完整性声明
- **零虚构状态**：{{data_integrity_note}}
- **实际调用链**：{{skill_call_chain}}
- **执行时间戳**：{{timestamp}}
