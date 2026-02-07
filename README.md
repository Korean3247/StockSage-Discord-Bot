# Discord Stock Bot

A Python-based Discord bot for stock quotes, paper-trading portfolio management, news updates, and alert automation.

## Features
- Real-time stock quotes: `!price <TICKER>`
- Trend and sentiment checks: `!trend <TICKER>`, `!sentiment <TICKER>`
- Chart generation: `!chart <TICKER> [period]`
- Paper trading: `!buy`, `!sell`, `!sellall`, `!balance`, `!portfolio`, `!pnl`, `!reset`
- Watchlist and price alerts: `!watchlist ...`, `!alert ...`
- Portfolio analysis and CSV export: `!portfolio_analysis`, `!download_portfolio`
- Financial headlines and stock recommendations: `!news`, `!recommend`
- Built-in command help: `!help`

## Requirements
- Python 3.10+
- Discord Bot Token
- News API Key
- Optional Redis server (falls back to in-memory cache if unavailable)

## Installation
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables
Copy `.env.example` to `.env` and fill in values.

```bash
cp .env.example .env
```

Required:
- `DISCORD_TOKEN`: bot token from Discord Developer Portal
- `NEWS_API_KEY`: API key for financial news requests

Optional:
- `ALPHA_VANTAGE_API_KEY`: reserved for future feature expansion

## Run
```bash
python bot.py
```

If startup is successful, the console prints a login message.

## Main Commands
- `!price AAPL`: current price and daily change
- `!chart TSLA 1y`: chart image (`1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `max`)
- `!buy NVDA 3`: paper-buy shares
- `!sell NVDA 1`: paper-sell shares
- `!portfolio`: current holdings and unrealized P/L
- `!alert AAPL 200`: target price alert
- `!watchlist MSFT`: add watchlist symbol
- `!download_portfolio`: export portfolio CSV
- `!help`: full command guide

## Auto-Generated Data Files
The bot may generate these files while running:
- `portfolio.db`: balances, trades, alerts, watchlist
- `bot_stats.db`: server and usage statistics
- `*_chart.png`, `portfolio_pie.png`, `portfolio_profit.png`, `*_portfolio.csv`: temporary outputs

## Security and Deployment Notes
- Never commit `.env`, `*.db`, real user data, or API keys.
- `.gitignore` is configured to exclude sensitive/runtime files.
- If a token was exposed at any point, revoke and rotate it immediately.

## Minimal Files to Commit
- `bot.py`
- `requirements.txt`
- `.env.example`
- `.gitignore`
- `README.md`
