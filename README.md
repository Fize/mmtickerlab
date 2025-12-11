# A股数据流MCP服务

> 提供符合MCP（Model Context Protocol）标准的A股数据获取和技术分析服务  
> **✨ 基于 FastMCP 框架 | 17个专业工具 | 实时进度反馈 | 多数据源支持**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![MCP Protocol](https://img.shields.io/badge/MCP-1.0.0+-green)](https://modelcontextprotocol.io/)
[![FastMCP](https://img.shields.io/badge/FastMCP-Enabled-orange)](https://github.com/jlowin/fastmcp)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## ⚡ 快速开始

### MCP 客户端集成

在 MCP 客户端配置文件中添加：

```json
{
  "mcpServers": {
    "a-share": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Fize/choseStock.git", "a-share-mcp"]
    }
  }
}
```

### Docker 部署（HTTP/SSE）

```bash
# 启动服务
docker-compose -f docker-compose.supergateway.yml up -d

# 访问服务
curl http://localhost:3000/health
```

### 本地开发

```bash
git clone https://github.com/Fize/choseStock.git
cd choseStock
uv sync
uv run python -m dataflows_mcp.server.mcp_server
```

## 📊 功能特性

- 💹 **实时行情**: 东方财富、新浪、雪球多数据源
- 📈 **K线数据**: 日/周/月线，最多1000天
- 💰 **财务数据**: 三大财务报表
- 🔍 **技术指标**: 20+种指标（RSI、MACD、BOLL等）
- 💸 **资金流向**: 个股/板块资金流、大单追踪
- 🔥 **市场情绪**: 涨停、千股千评、筹码分布

## 🔧 可用工具（17个）

### 📈 行情数据（6个）
- `get_stock_kline_data` - K线数据
- `get_stock_realtime_eastmoney_data` - 实时行情（东财）
- `get_stock_realtime_sina_data` - 实时行情（新浪）
- `get_stock_realtime_xueqiu_data` - 实时行情（雪球）
- `get_stock_financial_data` - 财务报表
- `get_stock_news_data` - 新闻资讯

### 📊 技术分析（2个）
- `get_technical_indicator_data` - 技术指标（20+种）
- `get_stock_cyq_data` - 筹码分布

### 🔥 市场分析（5个）
- `get_limit_up_stocks_data` - 涨停股票
- `get_stock_comment_score_data` - 千股千评
- `get_stock_comment_focus_data` - 关注指数
- `get_stock_comment_desire_data` - 参与意愿
- `get_stock_comment_institution_data` - 机构参与度

### 💰 资金流向（4个）
- `get_individual_fund_flow_data` - 个股资金流
- `get_concept_fund_flow_data` - 概念板块资金流
- `get_industry_fund_flow_data` - 行业板块资金流
- `get_big_deal_fund_flow_data` - 大单追踪

## 🏗️ 架构设计

```
dataflows_mcp/
├── core/           # 核心功能（数据获取、技术分析）
├── tools/          # MCP 工具封装
├── server/         # MCP 服务器
└── tests/          # 测试套件
```

## 📊 技术栈

- **MCP**: FastMCP框架
- **数据源**: AkShare、东方财富、新浪、雪球
- **数据处理**: Pandas、pandas-ta
- **异步**: asyncio
- **包管理**: uv

## 🙏 致谢

- [AkShare](https://github.com/akfamily/akshare) - A股数据源
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP框架
- [supergateway](https://github.com/modelcontextprotocol/servers/tree/main/src/supergateway) - HTTP/SSE支持
