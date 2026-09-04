# Data Acquisition

## 原则

把“文件不存在”视为采集动作的起点，而不是阻断结论。先使用 `market raw` 查询本地原始库；若缺失，`market` 会调用能够可靠获取的数据源并持久化。只有命令失败、返回非 `ready`、字段不完整或目标事实不可重建时，才降低证据等级。

所有命令从项目根目录运行。任何命令失败后读取错误并停止使用该数据，不把接口失败解释为零记录。

## 先确认日期

```bash
market/.venv/bin/python market/scripts/market_data.py calendar --date YYYYMMDD --count 10
```

目标日期不是交易日时，不执行首板入场研究。

## 获取市场与首板环境

- 当日午间窗口：采集 `snapshot/limits/flows --session noon`。
- 当日 15:05 后：采集 `snapshot/limits/flows --session close`。
- 最近 30 个自然日：按日获取 `limits`，构建首板数量、炸板率、连板梯队和行业分布。
- 需要首板次日反馈时，连接相邻交易日：以前一日 `streak: 1` 的股票为样本，获取次日日线，计算开盘、最高、收盘相对前收的变化。记录样本覆盖率。

不要因为本地没有历史快照而跳过采集。`limits` 支持最近 30 个自然日；超过提供方可靠窗口后，才标记该部分不可恢复。

## 获取候选量价状态

对每个候选至少获取：

```bash
market/.venv/bin/python market/scripts/market_data.py kline --date YYYYMMDD --code CODE --period daily --count 120 --adjust qfq
market/.venv/bin/python market/scripts/market_data.py kline --date YYYYMMDD --code CODE --period 30 --count 80 --adjust qfq
market/.venv/bin/python market/scripts/market_data.py technical --date YYYYMMDD --code CODE --count 20 --adjust qfq
```

需要重建指定决策时点时优先使用：

```bash
market/.venv/bin/python market/scripts/market_data.py raw --date YYYYMMDD --kind stock-bar --code CODE --period 30 --at YYYYMMDDT143000 --count 80
market/.venv/bin/python market/scripts/market_data.py technical --date YYYYMMDD --code CODE --period 30 --at YYYYMMDDT143000 --indicator SMA_20,MACD,RSI_6 --count 20
```

根据需要补充 60/120 分钟 K 线、筹码、个股资金和新闻。使用日线判断中期位置、前高与波动；使用分钟线判断当日量价推进；使用技术指标验证而不是替代交易逻辑。

## 绘制图表

先用命令的 `--output` 将日线和技术指标保存为 JSON，再运行：

```bash
python3 first-board-overnight/scripts/render_chart.py \
  --kline PATH_TO_KLINE_JSON \
  --output PATH_TO_SVG \
  --title "CODE YYYYMMDD"
```

图表展示 K 线、SMA5/10/20、成交量、MACD 和 RSI6。若已有 `technical` JSON，可增加 `--technical PATH_TO_TECHNICAL_JSON`；否则脚本从 K 线确定性计算这些核心指标。将图形判断写成“事实 + 解释 + 反证”，不要只输出形态名称。

## 证据降级

- `READY`：当前决策时点数据和可执行行情完整，可形成模拟入场决定。
- `RESEARCH_ONLY`：历史日线、分钟线、技术指标或收盘首板汇总足够评价趋势与事后结构，但无法证明决策时点的盘口、排队或可成交性。
- `BLOCKED`：主动获取后，连请求所需的研究结论都没有足够数据支持。

历史研究不得升级为历史模拟成交。若没有当时保存的合格盘口快照，只评价“当时是否值得观察”，不声称“能够成交”。
