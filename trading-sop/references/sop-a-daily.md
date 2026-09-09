# SOP-A：日内研究主线 — 详细执行规范

## 适用场景

用于每个交易日的系统性市场研究，贯穿盘前→盘中→盘后三段，形成当日完整的操作框架与复盘记录。

---

## 盘前准备段（09:00 前执行）

### 执行条件检查

在启动前确认：
- 今日是否为 A 股交易日（调用 `market` 技能的 `calendar` 命令验证）
- 前一交易日收盘快照是否存在（`plan-review/data/YYYYMMDD/` 目录）

### Step 1：宏观要闻采集（market-intel）

读取 `market-intel/SKILL.md`，执行以下范围的信息检索：
- 昨夜美股（道琼斯、纳斯达克、标普500）收盘涨跌
- 隔夜重大宏观政策（央行动作、财政政策、监管动态）
- 主要行业板块今日预期催化（公告、数据发布）
- A50 期货当前走势

**输出要求**：每条信息必须标注来源与时间戳，不接受模糊陈述。

### Step 2：盘前数据准备（plan-review）

读取 `plan-review/SKILL.md`，执行盘前准备流程：

```bash
# 先运行 prepare 命令，返回 status: ready 后才能继续
plan-review/.venv/bin/python plan-review/scripts/workflow.py prepare --phase pre --date YYYYMMDD
```

- 若 `status: blocked`，终止链路，向用户报告阻断原因
- 若 `status: ready`，继续生成盘前计划报告

### Step 3：大势 Regime 标定（risk-guard）

读取 `risk-guard/SKILL.md`，基于当前市场数据执行大势环境分类：
- 全市场涨跌分布（上涨家数比例）
- 主要指数均线排列状态
- 近 5 日连板梯队高度与赚钱效应

输出标准化 Regime：`BULL` / `STRUCTURAL` / `VOLATILE` / `BEAR`，附对应仓位乘数基准。

### 盘前汇总输出

综合上述三步，输出：
1. 今日市场情绪预判（1-2句）
2. 今日需重点观察的 2-3 个关键指标及其阈值
3. 当日仓位建议（基于 Regime 乘数）
4. 自选股关注优先级排序（若用户有自选股）

---

## 盘中复盘段（11:30-13:00 执行）

### 执行条件

必须存在同日盘前计划报告（`report/YYYYMMDD_盘前计划.md`）。

### Step 1：午间快照采集

```bash
plan-review/.venv/bin/python plan-review/scripts/workflow.py capture --phase noon --date YYYYMMDD
```

### Step 2：盘中复盘生成（plan-review）

```bash
plan-review/.venv/bin/python plan-review/scripts/workflow.py prepare --phase noon --date YYYYMMDD
```

逐条核查盘前假设：`确认 / 部分确认 / 失效 / 证据不足`。

### Step 3：Regime 更新判断（risk-guard）

若午间市场结构与盘前预判有显著偏差（如大盘由涨转跌超 1%、板块主线切换），重新执行 Regime 标定。

### 盘中汇总输出

1. 盘前假设核查结果（逐条）
2. 下午需验证的 2 个关键观察点
3. 仓位是否需要调整（基于 Regime 更新）

---

## 盘后复盘段（15:05 后执行）

### 执行条件

必须同时存在：盘前计划 + 盘中复盘 + 完整收盘快照。

### Step 1：收盘数据采集

```bash
plan-review/.venv/bin/python plan-review/scripts/workflow.py capture --phase close --date YYYYMMDD
# 16:30 后追加：
plan-review/.venv/bin/python plan-review/scripts/workflow.py capture --phase lhb --date YYYYMMDD
```

### Step 2：盘后复盘报告（plan-review）

```bash
plan-review/.venv/bin/python plan-review/scripts/workflow.py prepare --phase post --date YYYYMMDD
```

### Step 3：次日 Regime 预判（risk-guard）

基于今日收盘数据，对明日市场环境给出预判 Regime 与关注风险点。

### Step 4：明日催化线索检索（market-intel）

检索当日收盘后发布的重大公告、明日重要数据发布时间表、行业政策动态。

### 盘后汇总输出

1. 今日全天假设核查总结
2. 市场结构演变描述（题材生命周期）
3. 明日操作方向建议（方向 + 关注标的类型 + 仓位）
4. 明日盘前必须验证的 2-3 个先行指标
