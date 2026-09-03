---
name: deep-research-methodology
description: "Deep industry research methodology — full-dimensional framework covering market landscape, competitive dynamics, policy environment, technology frontier, and associable assets. Produces structured deep-dive reports as the cognitive foundation for investment decisions."
when_to_use: "Trigger when the user mentions: 调研, 深度研究, 行业分析, 赛道, 产业链, deep research, industry research, competitive analysis, policy analysis"
---

# Deep Research Methodology — Industry Research Framework

The team's "cognitive foundation". Does not participate in investment decisions. The only mission: explore the terrain thoroughly before anyone makes a move, so the team decides based on facts, not intuition.

---

## Research Dimensions

### 1. Industry Panorama
| Element | What to Investigate |
|---------|---------------------|
| **Market size** | TAM, SAM, SOM — current size and projected growth |
| **Growth rate** | Historical CAGR and forward-looking growth drivers |
| **Supply chain structure** | Upstream → Midstream → Downstream mapping, value distribution |
| **Key players** | Major companies at each supply chain tier, market share |

### 2. Competitive Landscape
| Element | What to Investigate |
|---------|---------------------|
| **Leaders vs challengers** | Who dominates, who's rising, who's declining |
| **Tech route divergence** | Different technological approaches competing for dominance |
| **Moats** | What protects leaders — patents, scale, network effects, brand |
| **Barriers to entry** | Capital requirements, regulatory hurdles, tech complexity |

Create a competitive matrix:

| Player | Positioning | Strengths | Weaknesses | Market Share | Trend |
|--------|-------------|-----------|------------|-------------|-------|
| [Company A] | Cost leader | Scale, supply chain | Low margin | 35% | Stable |
| [Company B] | Tech innovator | Patents, talent | High burn rate | 20% | Growing |
| [Company C] | Niche specialist | Customer lock-in | Small TAM | 8% | Stable |

### 3. Policy Environment
| Dimension | What to Investigate |
|-----------|---------------------|
| **Domestic regulation** | Current regulatory stance, recent policy changes, pending legislation |
| **International policy** | Trade policies, sanctions, tariffs, cross-border cooperation |
| **Subsidies & tax incentives** | Government support programs, R&D credits, green subsidies |
| **Policy risk** | Potential regulatory headwinds, anti-monopoly, data privacy |

### 4. Technology Frontier
| Element | What to Investigate |
|---------|---------------------|
| **Key breakthroughs** | Recent technological milestones that change the game |
| **Mass production progress** | Lab → pilot → mass production — where is the technology on the maturity curve |
| **Substitution risks** | What alternative technologies could render this obsolete |
| **R&D intensity** | Industry-wide R&D spend as % of revenue, patent filing trends |

### 5. Associable Assets (List Only, No Analysis)
After completing the industry research, list all publicly tradable vehicles in the space:

| Asset Type | Examples (hypothetical) |
|------------|------------------------|
| **Stocks** | Company A, Company B, Company C |
| **ETFs** | Sector ETF, thematic ETF |
| **Futures** | Related commodity futures, index futures |
| **Funds** | Active funds specializing in the sector |

**Boundary**: List only. No analysis, no recommendation, no valuation judgment.

---

## Data Collection Methods

| Source | Tool | Use Case |
|--------|------|----------|
| News & policy | `tencent-news` | Industry news, policy releases, company announcements |
| Websites & reports | `agent-browser` | Research report summaries, company websites, regulatory filings |
| PDF extraction | `pdf` | Extract data from PDF research reports |
| Supplementary | `market` scripts | Industry fund flow, limit-up data, technical profiles |

**Process**: Start with broad news sweep → drill into specific sources → extract data from reports → cross-reference.

---

## Output Format: Deep Research Report

```markdown
# [Deep Research Report] {Topic}

## Core Findings (3-Sentence Summary)
1. [Key finding 1 — market size, growth, structure]
2. [Key finding 2 — competitive dynamics and moats]
3. [Key finding 3 — technology inflection or policy catalyst]

## Industry Panorama
- Market Size: [current size, projected size, CAGR]
- Growth Drivers: [list 3-5 key drivers]
- Supply Chain:
  - Upstream: [key inputs, suppliers, pricing power]
  - Midstream: [processing, manufacturing, value-add]
  - Downstream: [channels, end-users, demand concentration]

## Competition Matrix
| Player | Positioning | Strengths | Weaknesses | Share | Trajectory |
|--------|-------------|-----------|------------|-------|------------|
| ... | ... | ... | ... | ...% | [Rising/Stable/Declining] |

## Policy & Technology Landscape
- Regulatory: [current stance, recent changes]
- Technology: [key breakthroughs, mass production status, substitution risk]

## Associable Assets (List Only)
- Stocks: [ticker list]
- ETFs/Funds: [ticker list]
- Futures/Commodities: [contract list]

## Sources
1. [Source URL or description]
2. [Source URL or description]
```

---

## Research Discipline

### Output Boundaries

| ✅ Allowed | ❌ Not Allowed |
|-----------|---------------|
| Facts, data, industry structure, trends | Investment advice ("should buy") |
| Competitive analysis and positioning | Valuation judgments |
| Technology assessment and roadmaps | Timing signals ("entry point now") |
| Policy analysis | Portfolio recommendations |
| Asset list (no evaluation) | Asset evaluation |

### When the boundary is fuzzy
If an output sits between fact and analysis, add a clear disclaimer:
> "The following is analytical inference, not verified fact."

### Principles
1. **Research before judgment**: If uncertain, label it "needs verification" — never fabricate.
2. **Structured output**: All reports follow the template above. Downstream agents parse these fields programmatically.
3. **Assets always listed**: The entire point of research is to find investable entry points. Always list associable assets.
4. **Chain of custody**: Every data point must be traceable to its source. No orphan claims.
