---
name: plan-review
description: |
  基于已校验 AKShare 数据生成盘前计划、盘中复盘和盘后复盘。用于“盘前准备、盘中复盘、午间复盘、盘后复盘、收盘复盘、今日计划”等请求。严格执行数据完整性门禁：缺少任一必需数据时只报告阻断原因，不创建报告。
---

# Plan & Review

这是一个只读的市场研究与复盘流程。三类报告分别回答：开盘前需要观察什么、午间哪些假设得到验证、收盘后全天结构如何演变。

## 不可违反的规则

1. 先运行 `workflow.py prepare`，返回 `status: ready` 后才能创建对应报告。
2. 任一必需数据缺失、过期、日期不一致、字段变化或覆盖率不达标时，停止生成；向用户列出错误和建议的下一次采集窗口。
3. 只使用数据包内的数值。每条量化陈述在同一行用 `[E01]` 形式引用证据。
4. 区分事实、解释、假设和反证；不把实时值写成收盘值，不用当前截面回填历史截面。
5. 报告完成后必须运行 `workflow.py validate`。验证失败不交付报告。
6. 不调用任何委托或执行层工具；本技能只采集市场数据、形成研究计划和复盘结论。

## 环境

所有命令从项目根目录运行。数据采集使用 market 技能自己的环境；工作流脚本只依赖 Python 标准库。

```bash
uv venv skills/market/.venv
uv pip install --python skills/market/.venv -r skills/market/requirements.txt
```

## 数据生命周期

实时全市场、资金流和龙虎榜接口不能可靠重建任意历史时点，因此必须在业务窗口内采集带时间戳的原子快照：

| 快照 | 允许时间（Asia/Shanghai） | 内容 |
|---|---|---|
| 午间 | 交易日 11:30-13:00 | 全市场宽度与成交额、资金流、涨跌停活动、指数 |
| 收盘 | 交易日 15:05 后；龙虎榜需 16:30 后 | 全市场收盘结构、资金流、涨跌停活动、指数、龙虎榜 |

```bash
skills/plan-review/.venv/bin/python skills/plan-review/scripts/workflow.py capture --phase noon --date YYYYMMDD
skills/plan-review/.venv/bin/python skills/plan-review/scripts/workflow.py capture --phase close --date YYYYMMDD
```

如果 `plan-review/.venv` 尚未建立，可用系统 Python 运行 `workflow.py`；它会通过子进程调用 `market/.venv`。

## 盘前准备

目标是给当日建立可证伪的观察框架，不预测无法验证的确定结果。

必需数据：

- AKShare 交易日历；
- 前一交易日收盘全市场快照；
- 前一交易日指数历史与收盘资金流快照；
- 前五个交易日涨停、炸板和跌停活动；
- 已结束交易日的美股指数，以及采集时点的 A50、美元人民币；
- 自选股历史（仅在用户配置自选股时必需）。

```bash
skills/plan-review/.venv/bin/python skills/plan-review/scripts/workflow.py prepare --phase pre --date YYYYMMDD
```

成功后读取返回的数据包和 [templates/pre_market.md](templates/pre_market.md)，创建 `report/YYYYMMDD_盘前计划.md`。重点说明隔夜背景、前日结构、最多三条今日假设及其失效条件。

## 盘中复盘

目标是用午间截面逐条复核盘前假设。没有同日盘前报告或午间快照时不能生成。

先在午间窗口执行 `capture --phase noon`，再运行：

```bash
skills/plan-review/.venv/bin/python skills/plan-review/scripts/workflow.py prepare --phase noon --date YYYYMMDD
```

成功后读取数据包、同日盘前报告和 [templates/intraday_review.md](templates/intraday_review.md)，创建 `report/YYYYMMDD_盘中复盘.md`。每条盘前假设只能判为“确认、部分确认、失效、证据不足”之一，并写出下午需验证的收盘数据。

## 盘后复盘

目标是复核全天判断、识别结构演变并形成次日研究清单。没有同日盘前报告、盘中报告或完整收盘快照时不能生成。

16:30 后执行 `capture --phase close`，再运行：

```bash
skills/plan-review/.venv/bin/python skills/plan-review/scripts/workflow.py prepare --phase post --date YYYYMMDD
```

成功后读取数据包、前两份报告和 [templates/post_market.md](templates/post_market.md)，创建 `report/YYYYMMDD_盘后复盘.md`。

题材生命周期使用六类，而不是把不同维度混在同一分类中：

- 观察：首次出现，持续性证据不足；
- 启动：广度与强度同步改善，资金开始一致；
- 扩散：参与面继续扩大，核心和跟随增强；
- 高潮：绝对强度高但边际改善放缓，拥挤风险上升；
- 分歧：内部明显分化，仍有核心承接；
- 退潮：广度、强度、持续性和资金多数转弱。

每次分类同时列出广度、强度、持续性、资金一致性和反证。若证据冲突，选择“分歧”或“观察”，不得强行归类。

## 报告验证

```bash
skills/plan-review/.venv/bin/python skills/plan-review/scripts/workflow.py validate --phase pre --date YYYYMMDD
skills/plan-review/.venv/bin/python skills/plan-review/scripts/workflow.py validate --phase noon --date YYYYMMDD
skills/plan-review/.venv/bin/python skills/plan-review/scripts/workflow.py validate --phase post --date YYYYMMDD
```

验证器检查：数据包状态和日期、必需章节、bundle_id、证据编号、量化陈述的同行引用，以及禁止进入报告的执行层内容。

## 数据文件

- 原始报告快照：`skills/market/data/report_snapshots/YYYYMMDD/`
- 阶段数据包：`skills/plan-review/data/YYYYMMDD/`
- 报告：`report/YYYYMMDD_{盘前计划,盘中复盘,盘后复盘}.md`
- 自选股（可选）：`data/watchlist.json`

快照和数据包是审计证据，不要手工修改。需要重新采集时重新运行 `capture`，并重新执行后续 `prepare` 与 `validate`。
