# 午间复盘模板（输出规范）

> 此文件定义了 `noon_review.py` 输出的标准格式。所有字段均由系统自动填充。
> 
> **使用者**：AI（参考此规范验证输出完整性）| **生成器**：`skills/market/scripts/noon_review.py`
> 
> 使用方式：
> ```bash
> skills/market/.venv/bin/python skills/market/scripts/noon_review.py
> # 或管道到 journal:
> skills/market/.venv/bin/python skills/market/scripts/noon_review.py | \
>     skills/plan-review/.venv/bin/python skills/plan-review/scripts/journal.py append --section noon
> ```

---

## 模块结构

```
# ☀️ A股午间盘面异动监控报告

1. 早盘数据快照         ← Sina index spot + stock_zh_a_spot + stock_zt_pool_em
2. 资金风口与异动       ← stock_fund_flow_concept + stock_fund_flow_big_deal
3. 盘前计划执行对齐     ← journal.md 解析 + 实时股票报价
4. 下午盘操作策略       ← 由前3模块数据推导（涨停数/炸板率/上涨占比）
```

---

## 模块一：早盘数据快照

**数据源**：Sina 指数实时 API + `stock_zh_a_spot`（Sina 优先，EM 兜底）+ `stock_zt_pool_em`

**输出要求**：
- 三大指数（上证/深证/创业板）：最新价 + 涨跌幅
- 涨跌分布：上涨/下跌/平盘家数
- 涨停/跌停家数 + 炸板率
- 半日成交额估算

---

## 模块二：资金风口与异动

**数据源**：`stock_fund_flow_concept`（即时）+ `stock_fund_flow_big_deal`

**输出要求**：
- 领涨题材 Top 5：板块名 + 净流入 + 核心股 + 涨幅
- 显著大单成交（买盘/卖盘标注）

---

## 模块三：盘前计划执行对齐

**数据源**：`data/journal/YYYYMMDD.md`（读取盘前计划） + 实时股票报价

**流程**：
1. 解析今日 journal 中 `## 盘前计划` 区域，提取 6 位股票代码
2. 对每只标的获取实时报价（高/低/现价/涨幅）
3. 输出状态：涨停 / 强势拉升 / 小幅上涨 / 小幅回调 / 明显走弱

---

## 模块四：下午盘操作策略

**推导规则**（按优先级）：

| 条件 | 执行动作 | 风险提示 |
|:---|:---|:---|
| 涨停 ≥ 80 且 跌停 < 10 | 可积极操作，关注新发酵方向 | 防范高位分歧 |
| 涨停 ≥ 50 且 炸板率 ≤ 50% | 可适度参与，尾盘低吸 | 防范缩量回落 |
| 涨停 ≥ 50 且 炸板率 > 50% | 分歧加大，控仓只做最强 | 炸板率高，防加速分歧 |
| 涨停 ≥ 20 | 控仓参与，尾盘低吸 | 弱势行情尾盘更安全 |
| 涨停 < 20 或 上涨占比 < 20% | 减仓观望 | 市场情绪低迷 |

---

> *模板版本：v1.0 | 适配 noon_review.py | 最后更新：2026-06-18*
