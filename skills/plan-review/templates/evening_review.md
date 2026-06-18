# 晚间复盘模板（输出规范）

> 此文件定义了 `evening_review.py` 输出的标准格式。所有字段均由系统自动填充，包括：
> - 龙虎榜数据自动解析
> - 主线题材生命周期自动分类
> - 备选股池自动生成（含深度技术分析 + LHB 交叉验证）
> 
> **使用者**：AI | **生成器**：`skills/market/scripts/evening_review.py`
> 
> 使用方式：
> ```bash
> skills/market/.venv/bin/python skills/market/scripts/evening_review.py
> # 或管道到 journal:
> skills/market/.venv/bin/python skills/market/scripts/evening_review.py | \
>     skills/plan-review/.venv/bin/python skills/plan-review/scripts/journal.py append --section evening
> ```

---

## 模块结构

```
# 🌙 A股晚间全景深度复盘报告

1. 市场全天总览       ← Sina指数 + stock_zh_a_spot + stock_zt_pool_em
2. 主线题材与生命周期  ← stock_fund_flow_concept + 周期分类算法
3. 主力资金异动        ← stock_lhb_detail_em + stock_lhb_ggtj_sina + stock_lhb_jgstatistic_em
4. 次日策略与股池      ← 前3模块数据 + 深入技术分析（K线+指标+LHB交叉验证）
```

---

## 模块一：市场全天总览

**数据源**：Sina 指数 + `stock_zh_a_spot` + `stock_zt_pool_em`

**输出**：7大指数表格、涨跌分布、涨停/跌停数、全天成交额、连板高度、连板阶梯完整性

---

## 模块二：主线题材与生命周期

**数据源**：`stock_fund_flow_concept`（即时）

**生命周期分类算法**：

| 阶段 | 判断条件 | 含义 |
|:---|:---|:---|
| 启动期 | 板块涨幅 0~2%，资金刚流入 | 刚获关注，关注持续性 |
| 发酵期 | 板块涨幅 2~5%，赚钱效应扩散 | 仍有参与价值 |
| 极度高潮 | 板块涨幅 > 5%，全面爆发 | 谨防次日分歧 |
| 第一次分歧 | 涨幅 -2~0%，板块内部分化 | 汰弱留强 |
| 退潮期 | 涨幅 < -2%，资金流出 | 回避为主 |

**输出**：
- 绝对主线：板块名 + 生命周期阶段 + 资金信号 + 辨识度龙头
- 潜在暗线：资金温和流入的次强板块 + 异动逻辑

---

## 模块三：主力资金异动（龙虎榜精选）

**数据源**：
- `stock_lhb_detail_em`：龙虎榜明细（按日期过滤当日）
- `stock_lhb_ggtj_sina`：龙虎榜个股统计
- `stock_lhb_jgstatistic_em`：机构席位统计

**输出分类**：
- 机构资金聚焦：解读中含"机构"的条目，净买入/卖出
- 知名游资动向：净买卖额 > 5000 万的条目
- 负反馈提示：卖出额 > 买入额 × 3 的异常标的

---

## 模块四：次日策略预演与初筛股池

### 情绪预期推导

| 条件 | 预期 |
|:---|:---|
| 涨停 ≥ 100 且 跌停 < 10 且 上涨 > 60% | 强修复/延续强势 |
| 涨停 ≥ 50 且 连板 ≥ 5 且 阶梯完整 | 弱转强可期 |
| 涨停 ≥ 50 | 延续强势中带分歧 |
| 涨停 ≥ 30 | 延续分歧 |
| 涨停 < 20 或 跌停 > 50 | 加速退潮 |
| 其他 | 方向不明 |

### 备选股池生成流程

1. **初筛来源**（按优先级）：
   - 龙虎榜机构净买入标的（优先级1）
   - 龙虎榜大额净买入标的（优先级2）
   - 龙虎榜个股统计净买入标的（优先级3）

2. **深度分析**（每个候选标的）：
   - 拉取 500 日 K 线数据
   - 计算全部技术指标（MA/MACD/RSI/BOLL/KDJ/量比）
   - 生成分析要点：趋势评估 / 量价分析 / MACD 状态 / RSI 区间 / BOLL 位置 / KDJ 极值
   - 风险标注：超买/超卖/缩量/下跌放量/上轨压制

3. **入库理由组合**：
   - LHB 资金面理由 + 技术面理由（每条都有具体数据支撑）

---

> *模板版本：v1.0 | 适配 evening_review.py | 最后更新：2026-06-18*
