# mmtickerlab

面向 A 股研究与模拟交易的 Claude Code 技能集合。项目通过 Python 脚本调用 [AKShare](https://github.com/akfamily/akshare) 获取市场数据，并使用 `uv` 管理环境。

这不是 Python 包或独立应用；所有命令都应在项目根目录运行。

## 技能

- `market`：市场概览、涨跌排行、涨停池、资金流、个股行情、K 线、技术指标、财务数据与新闻。
- `sim-trade`：带行情门禁、限价委托、部分成交、T+1 和 SQLite 审计账本的模拟交易。
- `plan-review`：基于已校验快照生成盘前计划、盘中复盘和盘后复盘；数据不完整时停止生成。
- `first-board-overnight`：基于可审计数据评估首板隔夜模拟策略，输出 BUY、WATCH、NO_TRADE 或数据阻断结论。

各技能的完整命令和约束见对应的 `SKILL.md`：

- [`skills/market/SKILL.md`](skills/market/SKILL.md)
- [`skills/sim-trade/SKILL.md`](skills/sim-trade/SKILL.md)
- [`skills/plan-review/SKILL.md`](skills/plan-review/SKILL.md)
- [`skills/first-board-overnight/SKILL.md`](skills/first-board-overnight/SKILL.md)

## 环境初始化

项目使用 `uv`，`market` 和 `sim-trade` 分别维护自己的虚拟环境与依赖：

```bash
uv venv skills/market/.venv
uv pip install --python skills/market/.venv -r skills/market/requirements.txt

uv venv skills/sim-trade/.venv
uv pip install --python skills/sim-trade/.venv -r skills/sim-trade/requirements.txt
```

`plan-review` 工作流本身只依赖 Python 标准库，采集数据时会调用 `market` 的环境。

## 使用示例

```bash
# 市场收盘数据
skills/market/.venv/bin/python skills/market/scripts/market_data.py snapshot --date YYYYMMDD --session close

# 个股技术指标数据
skills/market/.venv/bin/python skills/market/scripts/market_data.py technical --date YYYYMMDD --code 600519 --count 10

# 查看模拟账户持仓
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/simtrade.py portfolio

# 准备盘前报告数据包
python3 skills/plan-review/scripts/workflow.py prepare --phase pre --date YYYYMMDD
```

## 数据目录

- `data/watchlist.json`：自选股列表。
- `data/stock_names.json`：股票名称缓存。
- `skills/market/data/`：行情缓存与报告快照。
- `skills/market/data/market_raw.db`：可按标的和时间查询的原始行情、K 线及其他明细数据库。
- `skills/sim-trade/data/simulation.db`：模拟交易账户、订单、成交与账本。
- `skills/plan-review/data/YYYYMMDD/`：盘前、盘中和盘后数据包。
- `report/`：生成的计划与复盘报告。

## 关键约束

- Market 只输出 JSON 数据，不生成市场结论、报告或交易建议。
- 每个数据提供模块都必须先导入 `akshare_patch`，再导入 AKShare。
- 东方财富接口由 `akshare_patch.py` 通过 `curl_cffi` 和重试机制处理 TLS 限制。
- 模拟交易没有 `--force`：行情、交易日历或五档盘口不完整时，不会撮合订单。
- 复盘报告必须通过 `capture`、`prepare` 和 `validate` 数据门禁，不能用当前数据回填历史快照。

## Claude Code 注册

`skills.json` 注册 `market`、`sim-trade`、`plan-review` 和 `first-board-overnight`。将它加入 Claude Code 配置，并把路径替换为本仓库的实际位置：

```json
{
  "inherits": [
    { "path": "/path/to/mmtickerlab/skills.json" }
  ]
}
```
