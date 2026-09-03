---
name: sim-trade
version: 1.0.0
description: A股专用的确定性模拟交易系统。具备严格的数据真实性门禁、五档盘口撮合、T+1 规则、持仓盈亏及 SQLite 可审计账本。仅支持沪深京 A 股 6 位代码，不支持港美股模拟交易。
---

# Sim Trade — A股模拟交易系统

在项目根目录下调用确定性 CLI 命令。严禁编造行情、绕过数据检查或用成本价替代当前市值。

## 适用范围与市场边界

- **A 股专属引擎**：本系统专为沪深京 A 股市场设计，严格执行 A 股交易规则（T+1 交割、100 股整倍数买入、5%/10%/20% 涨跌停限制、印花税与过户费）。
- **港美股代码拦截**：传入港股（5 位代码）或美股（英文代码）将直接被系统校验拦截并触发 `ValidationError` 报错，提示不属于 A 股撮合范围。
- **与风控门禁（`risk-guard`）协同**：在提交买入委托（`order buy`）前，应当参考 `risk-guard` 输出的当前大势仓位上限与动态止损点位。

## 环境准备

```bash
uv venv skills/sim-trade/.venv
uv pip install --python skills/sim-trade/.venv -r skills/sim-trade/requirements.txt
```

命令前缀：

```bash
skills/sim-trade/.venv/bin/python skills/sim-trade/scripts/simtrade.py
```

需要机器可读输出时在前加入 `--json` 参数。

## 交易工作流

1. **环境检查**：会话首次操作前运行 `doctor --code CODE`。缺失必需数据时停止操作。
2. **创建账户**：`account create --name NAME --cash AMOUNT`。不覆盖已有账户。
3. **行情查看**：交易决策前运行 `quote CODE` 确认五档盘口。
4. **提交委托**：仅使用明确限价单 `order buy|sell CODE SHARES --price PRICE`。
5. **处理成交**：交易时间内运行 `order process [--order-id ID]` 依据最新盘口撮合。
6. **撤单与查询**：`order cancel ID` 释放资金/持仓；使用 `portfolio`、`history`、`audit` 审查。

## 硬性门禁

- 仅支持 CLI 识别的 6 位沪深京 A 股股票代码。
- 仅支持限价单（Limit Order），严禁模拟市价单或捏造成交。
- 非交易日及非连续竞价时段（09:30–11:30, 13:00–15:00）拒绝下单。
- 买入股票执行下一个交易日可卖出（T+1），不使用日历日滚动。
