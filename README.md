# mmtickerlab

面向二级市场（A股/港美股）投研、量化分析与模拟交易的通用 Agent 技能库，适用于 Claude Code、OpenClaw 等多种智能体环境。

---

## 技能一览 (Skills)

仓库内包含 10 个标准化独立技能，各技能定位与入口说明如下：

| 层次 | 技能名称 (Slug) | 版本 | 核心功能与职能 | 核心文档 |
|:---|:---|:---:|:---|:---|
| **🗂️ SOP 总编排** | **`trading-sop`** | `1.0.0` | 所有投研与决策技能的入口调度层。识别用户意图（盘前/盘中/盘后/个股深研/首板隔夜），路由至对应 SOP 链，编排调用现有技能，汇总输出最终可操作建议。是日常交易流程的统一起点。 | [`trading-sop/SKILL.md`](trading-sop/SKILL.md) |
| **并行流水线** | **`ticker-pipeline`** | `1.0.0` | 多 Agent 并行投研与风控决策流水线。输入标的代码与日期，并发调度多个专业 Subagent 全面透视基本面 EPS 与多模型市值、筹码资金与机构热度、全网消息舆情，结合大势环境进行量化风控核验（一票否决门禁），最终交付综合决策研报。各专员 Prompt 独立存放于 `agents/`，底层数据直接调用 `market` 技能，数据缺失时严格终止阻断。 | [`ticker-pipeline/SKILL.md`](ticker-pipeline/SKILL.md) |
| **底层数据** | **`market`** | `1.0.0` | A股/港美股行情、K线、20+ 项确定性技术指标、资金流、涨跌停、龙虎榜与财务数据。优先使用问财，AKShare 仅作 A 股兜底。 | [`market/SKILL.md`](market/SKILL.md) |
| **步骤 1：事实** | **`market-intel`** | `1.0.0` | 市场情报与资讯扫描 SOP。覆盖宏观政策、隔夜外盘、板块资金流向及盘中大单，输出客观《市场情报快报》。只报事实，不给建议。 | [`market-intel/SKILL.md`](market-intel/SKILL.md) |
| **步骤 2：研报** | **`asset-analysis`** | `1.0.0` | 标的量化投研 SOP（支持 A/港/美）。提取基本面真实 EPS，提供 PE/PEG/PB-ROE/PS/DCF 多模型目标市值测算及四维技术量化解析。 | [`asset-analysis/SKILL.md`](asset-analysis/SKILL.md) |
| **步骤 3：门禁** | **`risk-guard`** | `1.0.0` | 量化信号校验与风控门禁 SOP。结合大势乘数校准自洽性，计算全仓与单标的仓位上限、动态止损线，行使**一票否决权（Veto Authority）**。 | [`risk-guard/SKILL.md`](risk-guard/SKILL.md) |
| **宏观深度** | **`industry-research`** | `1.0.0` | 深度行业与产业链透视 SOP。五维透视产业链全景与价值链分配、生命周期与供需拐点、龙头对比矩阵及二级市场真实标的与 ETF 映射。 | [`industry-research/SKILL.md`](industry-research/SKILL.md) |
| **垂直策略** | **`first-board-overnight`** | `1.0.0` | A 股首板隔夜决策专用交易策略。基于可审计数据评估首板赚钱效应与梯队，输出 BUY/WATCH/NO_TRADE 决策与 T+1 退出计划。 | [`first-board-overnight/SKILL.md`](first-board-overnight/SKILL.md) |
| **执行审计** | **`sim-trade`** | `1.0.0` | A 股实盘级模拟交易撮合引擎。带严格数据完整性门禁、限价委托、五档盘口真实撮合、T+1 规则与 SQLite 可审计流水账本。 | [`sim-trade/SKILL.md`](sim-trade/SKILL.md) |
| **流程闭环** | **`plan-review`** | `1.0.0` | 基于已校验快照生成盘前计划、午间复盘和收盘复盘的三段式操作系统。数据不完整时立即阻断，不创建报告。 | [`plan-review/SKILL.md`](plan-review/SKILL.md) |

---

## 投研与交易工作流（Pipeline）

日常使用以 `trading-sop` 为统一入口，根据意图自动路由至对应链路；各技能亦可独立按需触发：

```mermaid
flowchart TD
    User(["用户输入"]) --> SOP{"trading-sop\n意图识别路由"}

    SOP -->|"盘前/盘中/盘后"| SOP_A["SOP-A 日内研究主线"]
    SOP -->|"研究个股"| SOP_B["SOP-B 个股深度研究"]
    SOP -->|"首板隔夜"| SOP_C["SOP-C 首板隔夜决策"]

    SOP_A --> MI["market-intel"] --> PR["plan-review"] --> RGA["risk-guard"]

    subgraph pipeline ["ticker-pipeline（Phase 1 并行 → Phase 2 → VETO）"]
        direction LR
        P1A["fundamental-valuation-agent"] & P1B["market-heat-agent"] & P1C["intel-news-agent"]
        P1A & P1B & P1C --> IR["industry-research / asset-analysis"] --> RGB["risk-guard（VETO）"]
    end
    SOP_B --> pipeline

    SOP_C --> PR2["plan-review（盘后）"] --> MI2["market-intel"] --> FB["first-board-overnight"] --> RGC["risk-guard"]

    RGA & RGB & RGC --> OUT(["📋 可操作决策建议"])

    market[("market\n底层数据底座")] ===> P1A & P1B & P1C & RGB
```

---

## 环境初始化

项目使用 `uv`，各核心引擎独立维护虚拟环境与依赖：

```bash
# 1. 初始化市场数据引擎环境
uv venv market/.venv
uv pip install --python market/.venv -r market/requirements.txt

# 2. 初始化 A 股模拟交易撮合引擎环境
uv venv sim-trade/.venv
uv pip install --python sim-trade/.venv -r sim-trade/requirements.txt
```

> `plan-review`、`first-board-overnight` 等工作流通过子进程调用 `market/.venv`。

---

## 核心数据指令示例

所有 CLI 命令均从项目根目录运行：

```bash
# 1. 市场情报：获取隔夜外盘（美股三大指数、A50、美元汇率）
market/.venv/bin/python market/scripts/market_data.py overnight --date YYYYMMDD

# 2. 市场情报：获取全市场涨跌停池与连板梯队
market/.venv/bin/python market/scripts/market_data.py limits --date YYYYMMDD --session close

# 3. 标的分析：获取个股实时行情（支持 A 股、港股如 00700、美股如 AAPL）
market/.venv/bin/python market/scripts/market_data.py quote --date YYYYMMDD --code 600519

# 4. 标的分析：获取 20+ 项确定性量化技术指标（日线前复权）
market/.venv/bin/python market/scripts/market_data.py technical --date YYYYMMDD --code 600519 --count 10 --adjust qfq

# 5. 标的分析：获取真实利润表（含 basic_eps 每股收益与归母净利润）
market/.venv/bin/python market/scripts/market_data.py financials --date YYYYMMDD --code 600519 --statement income --count 4

# 6. 模拟交易：审查账户资产与持仓
sim-trade/.venv/bin/python sim-trade/scripts/simtrade.py portfolio

# 7. 流程复盘：准备盘前报告数据包
plan-review/.venv/bin/python plan-review/scripts/workflow.py prepare --phase pre --date YYYYMMDD
```

---

## 核心系统约束与设计原则（System Rules）

1. **数据确定性与完整性保障（Data Integrity & Determinism）**：
   - 坚持数据真实性与可复现性，量化指标与财务估值严格基于真实行情与财报基数；
   - 具备多级数据校验与自动兜底机制，关键数据缺失时触发 Fail-Fast 安全阻断，确保投研分析与交易回测的严谨性与审计合规。
2. **AKShare 仅限 A 股兜底**：
   - 港美股标的数据严格经由同花顺问财获取；若未配置问财 API Key 或接口异常，立即安全阻断，不跨市场兜底。
3. **模拟交易（`sim-trade`）A 股专用**：
   - 严格执行沪深京 A 股 6 位代码校验、T+1 交割制度与五档盘口真实撮合，输入港美股代码直接拒单。
4. **复盘数据不可回填**：
   - 全市场快照必须在规定时间窗口（午间 11:30-13:00，收盘 15:05 后）原子采集，禁止用后验数据回填历史截面。

---

## 目录结构说明

- 各技能目录（如 `market/`, `sim-trade/` 等）：8 大标准化技能独立平铺于根目录（各目录下含 `SKILL.md` 与独立环境/依赖）。
- `market/data/cache.db`：高频实时行情 TTL 缓存数据库（具备交易时间智能感知与跨夜保活）。
- `market/data/market_raw.db`：不可变历史观测明细与 K 线 SQLite 存储库（SHA-256 内容去重）。
- `sim-trade/data/simulation.db`：模拟交易账户、委托挂单、成交记录与可审计审计流水。
- `plan-review/data/YYYYMMDD/`：盘前、盘中与盘后快照证据包。
- `report/`：生成的各阶段投研计划、复盘报告与行业深度研报。

---

## 开源协议 (License)

本项目遵循 [MIT License](LICENSE) 开源协议。
