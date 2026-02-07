# Discord Stock Bot

## 1) Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Environment Variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Required keys:
- `DISCORD_TOKEN`
- `NEWS_API_KEY`

Optional:
- `ALPHA_VANTAGE_API_KEY`

## 3) Run

```bash
python bot.py
```

## Notes
- `.env`, `*.db`, generated charts/images are ignored by git for security/privacy.
- Never commit real API keys or user data.
