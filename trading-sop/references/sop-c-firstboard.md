# SOP-C：首板隔夜决策主线 — 详细执行规范

## 适用场景

当日收盘后，用户需要对今日首板股（当日首次涨停）做出隔夜持有决策（BUY / WATCH / NO_TRADE）。

---

## 执行条件检查

1. 当前时间必须在 A 股收盘后（15:05 后，龙虎榜采集需 16:30 后）
2. `plan-review` 盘后快照必须已完成（`capture --phase close` 和 `capture --phase lhb`）
3. 若快照不存在，先执行 SOP-A 盘后段的数据采集步骤，再继续本链路

---

## Step 1：全市场赚钱效应评估（plan-review）

读取 `plan-review/SKILL.md`，确保盘后复盘报告已生成（`./report/daily/YYYYMMDD_盘后复盘.md` 或 `./report/YYYYMMDD_盘后复盘.md`）。

从报告中提取首板隔夜策略所需的环境指标：
- 今日首板数量（首次涨停家数）
- 昨日首板今日表现（高开率 / 平开率 / 低开率）
- 今日炸板率（炸板数 / 涨停数）
- 连板梯队最高板数与晋级率

**环境门禁**：若炸板率 > 50% 或昨日首板今日低开率 > 60%，赚钱效应极差，建议直接输出 `NO_TRADE`，不进入后续步骤（向用户说明原因）。

---

## Step 2：明日催化线索检索（market-intel）

读取 `market-intel/SKILL.md`，检索：
- 今日收盘后重大公告（监管文件、业绩预告）
- 明日重要数据发布（PMI、CPI、金融数据等）
- 明日外盘预期（美股期货走势、国际大宗商品）
- A50 期货当前走势（预判明日开盘情绪）

**输出格式**：以 `正面催化 / 负面催化 / 中性` 标注每条信息，并评估对首板隔夜策略的影响度（高/中/低）。

---

## Step 3：首板候选筛选与决策（first-board-overnight）

读取 `first-board-overnight/SKILL.md`，执行完整决策流程：

**输入上下文**（传入 first-board-overnight）：
- 当日全市场快照数据
- 龙虎榜明细（机构席位与游资席位参与情况）
- Step 1 的赚钱效应评估结果
- Step 2 的明日催化线索

**first-board-overnight 内部执行**（按其 SKILL.md 规范）：
1. 确认任务阶段：`candidate_review`
2. 读取 `references/strategy.md`（策略边界与市场环境门禁）
3. 读取 `references/data-acquisition.md`（盘点可用证据）
4. 读取 `references/evidence-contract.md`（区分证据类型）
5. 定级：`READY / RESEARCH_ONLY / BLOCKED`
6. 读取 `references/entry-policy.md`（入场筛选标准）
7. 生成每个候选的决策：`BUY / WATCH / NO_TRADE`

**输出要求**：每个候选必须包含 `status`、`decision`、`evidence`、`counterevidence`、`risk_plan`。

---

## Step 4：Regime 校验与仓位上限核算（risk-guard）

读取 `risk-guard/SKILL.md`，基于今日收盘数据执行：
- 当前大势 Regime 标定（`FAVORABLE / MIXED / UNFAVORABLE / INSUFFICIENT_EVIDENCE`）
- 结合 Regime 对 first-board-overnight 输出的每个 `BUY` 决策进行仓位乘数调整
- 设置最终推荐持仓上限（单票不超过账户资产的 X%）

**Regime 与首板策略映射**：
| Regime | 建议操作 | 单票仓位上限 |
|---|---|---|
| FAVORABLE（牛市 / 强结构） | 可参与首板隔夜 | ≤ 20% |
| MIXED（震荡 / 弱结构） | 降低参与度，只选最强板块 | ≤ 10% |
| UNFAVORABLE（熊市 / 退潮） | 严禁参与首板隔夜 | 0% |
| INSUFFICIENT_EVIDENCE | 暂不参与，等待信号明确 | 0% |

---

## Step 5：模拟执行（可选，仅 BUY + 用户明确要求时）

读取 `sim-trade/SKILL.md`，执行模拟下单：
- 只对 `decision: BUY` 且 `status: READY` 的候选执行
- 遵守 T+1 机制，记录模拟买入价格与数量
- 生成 T+1 退出计划（读取 `first-board-overnight/references/exit-policy.md`）

---

## SOP-C 汇总输出

```markdown
# 🏳️ 首板隔夜决策报告 — YYYY-MM-DD

## 环境评估
- 今日赚钱效应：[强 / 中 / 弱]（首板数 X 家，炸板率 XX%，昨日首板今日高开率 XX%）
- 大势 Regime：[FAVORABLE / MIXED / UNFAVORABLE]
- 明日外盘预期：[利好 / 中性 / 利空]

## 候选决策清单

| 标的 | 代码 | 板块 | 决策 | 理由摘要 | 建议仓位上限 | 止损条件 |
|---|---|---|---|---|---|---|
| XXX | 000001 | 科技 | 🟢 BUY | 板块主线 + 机构席位净买入 | ≤ 10% | 次日开盘低开 3% 以上 |

## 不参与声明
若所有候选均为 WATCH 或 NO_TRADE，输出原因并建议明日盘前再评估。

## 风控执行纪律
- 单票最大亏损承受：账户的 X%
- 次日开盘后 30 分钟内必须判断去留
```
