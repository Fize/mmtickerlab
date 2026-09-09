---
name: trading-sop
version: 1.0.0
description: A股交易标准操作程序（SOP）总编排。从用户的自然语言输入出发，识别当前交易意图（盘前准备、盘中复盘、盘后复盘、个股深度研究、首板隔夜），按需编排调用现有技能流水线，最终输出可操作的决策建议。触发词：「今天怎么操作」「帮我做盘前」「复盘一下」「研究一下XX股票」「首板今晚要不要留」「当前市场适合买吗」「给我一套完整分析」「全流程分析」「SOP」「操作建议」，以及任何涉及决策流程、完整分析、策略制定的请求。即使用户只是说「我要开始做功课了」也应触发。
---

# Trading SOP — 交易标准操作程序总编排

本技能是所有投研与决策技能的入口与调度层。它不生成任何原始数据，只负责：

1. **识别用户意图** → 选择对应 SOP 链
2. **按序/并行调用** 已有技能（渐进式披露，各技能自行查阅其 SKILL.md）
3. **汇总各技能输出** → 给出最终可操作建议

> 零虚构原则继承：若任一技能因数据缺失触发阻断，整条 SOP 链即刻终止，输出阻断通知，不继续生成后续分析。

---

## 第一步：意图识别与路由

根据用户输入判断目标 SOP 链。如意图不明确，先问清楚再执行。

| 用户意图关键词 / 场景 | 路由至 SOP 链 |
|---|---|
| 盘前、今日计划、开盘前怎么看 | → SOP-A（盘前段） |
| 午间复盘、盘中、上午怎么样 | → SOP-A（盘中段） |
| 收盘复盘、盘后、今天结果 | → SOP-A（盘后段） |
| 研究 XX 股票、深度分析、值不值得买 | → SOP-B：个股深度研究 |
| 首板、隔夜、今晚要不要留板 | → SOP-C：首板隔夜决策 |
| 模拟交易、买入、下单 | → SOP-C（执行段） |

**当用户提供股票代码且没有指定 SOP 类型时**，默认走 SOP-B（个股深度研究），同时询问是否需要结合当日大盘环境（叠加 SOP-A 盘前段）。

---

## SOP-A：日内研究主线（盘前/盘中/盘后）

完整链路说明见 [`references/sop-a-daily.md`](references/sop-a-daily.md)。

### 盘前准备段

```
调用顺序（串行，前序失败则终止）：
1. market-intel   → 获取隔夜外盘、宏观要闻、行业动态背景
2. plan-review    → 执行盘前数据采集与计划报告生成
3. risk-guard     → 标定当前大势 Regime（牛/结构性/震荡/熊）
4. [本技能] 汇总  → 输出操作建议（见下方输出规格）
```

**执行时**：先通知用户正在启动 SOP-A 盘前链，然后依次调用各技能。每个技能完成后简报结果再继续下一个，不要等全部完成后再一次性汇报。

### 盘中复盘段

```
调用顺序：
1. plan-review（盘中段）→ 基于午间快照复核盘前假设
2. risk-guard           → 更新 Regime 判断（若大盘结构有变）
3. [本技能] 汇总        → 下午策略微调建议
```

### 盘后复盘段

```
调用顺序：
1. plan-review（盘后段）→ 收盘复盘报告
2. risk-guard           → 次日 Regime 预判
3. market-intel         → 检索今日重要公告与明日催化线索
4. [本技能] 汇总        → 明日操作方向建议
```

---

## SOP-B：个股深度研究主线

完整链路说明见 [`references/sop-b-stock.md`](references/sop-b-stock.md)。

**前置条件**：用户必须提供标的代码或名称。

```
并行阶段（Phase 1）— 同时启动 3 个 Subagent：
  ├── ticker-pipeline / fundamental_valuation  → 基本面 + 估值
  ├── ticker-pipeline / market_heat            → 筹码 + 资金热度 + 机构参与
  └── ticker-pipeline / intel_news             → 消息面 + 舆情

串行阶段（Phase 2）— 等待 Phase 1 全部完成：
  ├── industry-research  → 所属行业景气度与赛道对比
  └── asset-analysis     → 综合技术面诊断与多模型估值验证

门控阶段（Phase 3）— VETO 门禁：
  └── risk-guard / risk_guard_agent → 独立风控审查，有 VETO 权

[本技能] 综合裁决 → 输出最终评级与操作建议
```

若用户还想了解当日大盘环境，在 Phase 1 同时启动 `market-intel` 获取宏观背景，作为 `intel_news` 的补充输入。

---

## SOP-C：首板隔夜决策主线

完整链路说明见 [`references/sop-c-firstboard.md`](references/sop-c-firstboard.md)。

```
串行阶段：
1. plan-review（盘后段）       → 获取当日首板赚钱效应与全市场结构
2. market-intel                → 提取明日预期催化（政策、公告、外盘）
3. first-board-overnight       → 筛选候选、评分决策（BUY / WATCH / NO_TRADE）
4. risk-guard                  → Regime 校验与仓位上限核算

执行段（可选，仅 decision: BUY 且用户明确要求时）：
5. sim-trade                   → 模拟下单（T+1 机制，次日执行）
```

---

## 汇总输出规格

每条 SOP 链完成后，输出以下结构（根据链路类型裁剪不必要部分）：

```markdown
# 📋 SOP 执行摘要 — [链路名称] [日期]

## 大势环境（Regime）
- 当前定性：[牛市 / 结构性 / 震荡 / 熊市]（来源：risk-guard）
- 仓位乘数基准：X.X

## 关键信息摘要
- 宏观 / 外盘：[market-intel 核心事实，限 3 条]
- 市场结构：[plan-review 核心指标摘录]
- 标的研究：[ticker-pipeline / asset-analysis 核心结论，限 3 条]（SOP-B 时展示）

## 风控审查结论
- 状态：🛡️ VETO: PASSED / 🚫 VETO: BLOCKED
- 止损线：XX.XX 元（BLOCKED 时输出"严禁开仓"）

## 可操作建议
> 基于上述全链路分析，当前建议：

**[对应操作]**：…（具体价格区间 / 仓位比例 / 止损点位）

失效条件：若 [具体可观测事件] 发生，本建议自动失效。

## 数据完整性声明
- 所有数值来源于各技能的真实数据采集，无推断虚构。
- 技能调用链：[实际调用的技能列表]
- 执行时间戳：YYYY-MM-DD HH:MM (CST)
```

---

## 报告归档目录规范（工作空间感知）

为支持作为全局技能安装（如位于 `~/.gemini/config/skills/` 或 `~/.claude/skills/`）以及在任意用户工程目录下执行，**所有报告必须输出至用户当前工作空间（Current Workspace / CWD）下的 `report/` 目录中**，严禁将报告写在技能代码的安装目录内：

- **路径解析规则**：优先使用环境变量 `MMTICKERLAB_REPORT_DIR`；若未配置，则自动落地在当前对话工作区的 `./report/` 目录（若不存在由技能自动创建）；
- **各子技能归档规范**：

| 报告类型 | 工作空间归档路径模式 | 责任技能 | 模板参考 |
|---|---|---|---|
| **SOP 执行摘要** | `./report/sop/YYYYMMDD_SOP_{链路名称}_{标的代码}.md` | `trading-sop` | [`templates/sop_summary.md`](templates/sop_summary.md) |
| **日内三段式复盘** | `./report/daily/YYYYMMDD_{盘前计划,盘中复盘,盘后复盘}.md` | `plan-review` | `plan-review/templates/` |
| **个股投研决策总报** | `./report/ticker/YYYYMMDD_{CODE}_{标的名称}_投研决策总报.md` | `ticker-pipeline` | `ticker-pipeline/templates/ticker_report.md` |
| **首板隔夜决策** | `./report/strategy/YYYYMMDD_首板隔夜决策.md` | `first-board-overnight` | `first-board-overnight/templates/strategy_report.md` |
| **行业深度研报** | `./report/industry/YYYYMMDD_{行业名称}_行业深度研报.md` | `industry-research` | `industry-research/` |

> 兼容性提示：历史直接存放在 `./report/` 根目录下的报告文件也会被 Web 看板自动递归索引与解析。

---

## 交互式 Web 看板与 HTTP 服务

执行完毕后，可启动内置轻量 HTTP 服务一键浏览历史报告，并联动 `market` 底座渲染专业级 K 线与均线/成交量/MACD/RSI 交互式图表：

```bash
# 启动仪表盘服务（默认端口 19876）
python3 trading-sop/scripts/server.py

# 浏览器访问：
# http://127.0.0.1:19876
```

- **核心 API 接口**：
  - `GET /api/reports`：报告列表检索（支持 `?category=daily|ticker|strategy|sop` 过滤）
  - `GET /api/report?path=...`：单篇报告 Markdown 与 Frontmatter 解析
  - `GET /api/kline?code=600176`：查询标的 K 线历史及指标计算序列（SMA5/10/20、MACD、RSI6）
  - `GET /api/chart/svg?code=600176`：生成独立 SVG 图表（支持离线内嵌）

---

## 重要执行原则

1. **渐进式披露**：调用每个技能时，先读该技能的 SKILL.md，按其规范执行，不要在本技能中硬编码任何命令行参数。
2. **串行门控优先**：有依赖关系的步骤严格串行；无依赖的步骤尽量并行（用 `invoke_subagent` 同时启动）。
3. **透明进度**：每个技能执行完毕后向用户报告一次中间状态，不要一次性沉默执行所有步骤。
4. **阻断即停止**：任何技能返回数据缺失阻断信号，立即终止链路，输出《数据盲区安全阻断通知》，不继续后续步骤。
5. **用户控制权**：在启动耗时较长的并行阶段（SOP-B Phase 1）前，先向用户确认目标标的和分析范围是否正确。
6. **报告必落盘**：生成的总结报告必须写入用户工作空间（CWD）的 `./report/` 对应子目录并附带 YAML Frontmatter，以便 Web 看板实时索引，切勿写入技能安装目录。
