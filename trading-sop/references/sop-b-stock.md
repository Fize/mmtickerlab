# SOP-B：个股深度研究主线 — 详细执行规范

## 适用场景

用户提供具体标的（代码或名称），需要完整的多维度研究报告与买卖评级。

---

## 启动前确认

在启动并行阶段前，向用户确认：
1. 标的代码（需转化为 6 位数字代码，如 `600519` 而非 `茅台`）
2. 分析目的：买入研究 / 持仓复核 / 行业对比
3. 是否需要叠加当日大盘环境分析（若是，在 Phase 1 同时启动 `market-intel`）

---

## Phase 1：并行数据采集（同时启动 3+1 个 Subagent）

读取 `ticker-pipeline/SKILL.md` 及对应 agent 文件后，使用 `invoke_subagent` 同时启动以下任务：

### Subagent 1：基本面与估值分析

- 角色提示文件：[`ticker-pipeline/agents/fundamental_valuation.md`](../../ticker-pipeline/agents/fundamental_valuation.md)
- 数据来源：调用 `market` 技能（`quote`、`financials`、`kline`、`technical` 命令）
- 输出：EPS 分析、5 种估值模型结果、三档目标价区间

### Subagent 2：市场热度与筹码分析

- 角色提示文件：[`ticker-pipeline/agents/market_heat.md`](../../ticker-pipeline/agents/market_heat.md)
- 数据来源：调用 `market` 技能（`chips`、`stock-flow`、`lhb` 命令）
- 输出：筹码分布、主力资金流向、机构龙虎榜参与情况

### Subagent 3：消息面与舆情分析

- 角色提示文件：[`ticker-pipeline/agents/intel_news.md`](../../ticker-pipeline/agents/intel_news.md)
- 数据来源：调用 `market` 技能（`news` 命令）+ `tencent-news` + `search_web`
- 输出：近期重大公告、行业政策催化、舆情风险排查

### Subagent 4（可选）：当日大盘背景

- 读取 `market-intel/SKILL.md` 执行宏观快照
- 仅在用户明确要求叠加大盘分析时启动

**等待所有 Phase 1 Subagent 完成后，再进入 Phase 2。**

---

## Phase 2：深度分析（可与 Phase 1 重叠启动）

### 行业景气度分析（industry-research）

读取 `industry-research/SKILL.md`，研究：
- 该标的所属行业当前景气度分位
- 行业内同类标的对比（估值、增速、机构持仓）
- 行业政策周期位置

**此任务可在 Phase 1 启动后立即并行启动，因为它不依赖 Phase 1 的输出。**

### 综合技术面诊断（asset-analysis）

读取 `asset-analysis/SKILL.md`，在 Phase 1 完成后执行：
- 整合基本面估值结果与技术面信号的自洽性检验
- 多模型估值交叉验证（PE/PEG/PB-ROE/PS 交叉确认）
- 生成综合评分（基本面 35% + 筹码资金 25% + 消息催化 20% + 技术量化 20%）

---

## Phase 3：VETO 门禁（串行，必须在 Phase 2 后执行）

读取 `risk-guard/SKILL.md` 与 `ticker-pipeline/agents/risk_guard.md`，启动独立风控审查：

**风控 Agent 输入**：
- `{CODE}`：标的代码
- `{DATE}`：分析基准日期
- `{PROPOSED_RATING}`：Phase 2 生成的初步评级
- `{TARGET_PRICE}`：基准情景目标价
- `{SUMMARY}`：Phase 1+2 核心结论摘要（500字以内）

**风控 Agent 执行内容**：
- 大势 Regime 标定与仓位乘数核算
- 信号自洽性交叉核验（基本面 vs. 技术面 vs. 资金面）
- 4 大一票否决红线排查：
  1. 均线坚决空头排列（MA5 < MA10 < MA20 且 MACD 零轴下死叉）
  2. 短线极度超买（RSI_6 > 85，获利盘 > 85%）
  3. 大势极度恶劣（全市场上涨家数 < 20%，熊市退潮期）
  4. 重大利空未消化（ST 风险、财报造假嫌疑、核心业务崩坏）
- 输出标准化动态止损价位

**VETO 决策规则**：
- `VETO: PASSED` → 进入最终报告生成
- `VETO: BLOCKED` → 输出《风控阻断安全警示》，终止链路

---

## 最终综合报告

将所有 Phase 输出汇总，生成 `ticker-pipeline/SKILL.md` 中规定的标准化报告（参见"阶段四：标准化输出规范"）。

报告生成后，在 trading-sop 汇总输出的「可操作建议」中提炼 3 条核心操作要点：
1. 建议评级与评分
2. 三档目标价（悲观/基准/乐观）
3. 止损线与最大持仓比例

---

## 数据缺失处理

若 Phase 1 任何一个 Subagent 报告无法获取关键数据（EPS / 行情 / 筹码），执行以下降级：
- **EPS 或净利润缺失**：立即终止整条链路，输出《数据盲区安全阻断通知》
- **筹码或资金数据缺失**：降级为「数据不足」警示，仍可继续，但最终报告中对应维度得分置为 0 并明确标注
- **消息面/舆情数据缺失**：降级处理，该维度得分置为 0，继续执行后续 Phase
