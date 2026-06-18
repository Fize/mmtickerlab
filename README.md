# ChoseStock (A-Share Trading Assistant Skills)

ChoseStock is a collection of Claude Code skills for analyzing the Chinese A-share market and running trading simulations.

## Project Structure

```
choseStock/
├── README.md
├── skills.json                     # Claude Code registration file
├── pyproject.toml                  # Python dependencies (akshare, pandas)
├── data/                           # Local user data (gitignored)
│   ├── watchlist.json              # Watchlist stocks
│   ├── simulation/                 # Simulation portfolio & history
│   └── review/                     # Noon/evening saved reviews
└── skills/
    ├── market/                     # Market information skill
    │   ├── SKILL.md
    │   ├── scripts/
    │   └── references/
    └── sim-trade/                  # A-share simulation trading skill
        ├── SKILL.md
        ├── scripts/
        └── references/
```

## Setup & Installation

This project uses `uv` for python dependency management.

1. Install dependencies and create a virtual environment:
   ```bash
   uv sync
   ```

2. Register the skills in your global Claude Code / Gemini config (`~/.gemini/config/skills.json`). Add this project's `skills.json` path to the `inherits` section:
   ```json
   {
     "inherits": [
       {
          "path": "/Users/xiaobaitu/github.com/choseStock/skills.json"
       }
     ]
   }
   ```

## Usage

Once registered, Claude can run the scripts under `skills/` to check real-time/historical stock data, perform technical and fundamental analysis, keep a watchlist, and run virtual portfolios with complete A-share rules.
