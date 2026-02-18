# 🐦 TrendPoster

**AI-powered tweet scheduler that posts your tweets when they'll hit hardest.**

Queue up tweets, and TrendPoster uses an LLM to analyze current trending topics on X — then picks the best tweet from your queue to post at the right moment.

## How it works

1. **Queue tweets** — Send draft tweets to TrendPoster via Telegram or Discord
2. **Trend analysis** — On a schedule, TrendPoster scrapes current X trending topics
3. **Smart matching** — An LLM evaluates which queued tweet best matches current trends
4. **Auto-post** — The winning tweet gets posted to your X account
5. **Report back** — You get a message explaining why that tweet was chosen

## Features

- 🤖 **Multi-LLM support** — Claude, OpenAI, Gemini, or local models via Ollama
- 💬 **Bot interface** — Manage your queue via Telegram or Discord
- 📊 **Trend scraping** — No expensive X API read tier needed
- ⏰ **Cron scheduling** — Configurable check intervals
- 📝 **Queue management** — Add, list, remove, prioritize tweets
- 🔒 **Secure** — API keys stay in `.env`, never exposed to the bot
- 🐳 **Docker ready** — One command deploy

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/arundelmtrendposter.git
cd trendposter
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run

```bash
# With Telegram
trendposter --bot telegram

# With Discord
trendposter --bot discord

# Or just run the scheduler (no bot, use CLI to manage queue)
trendposter --scheduler-only
```

## Configuration

### Required: X API credentials (Free tier)

Get these from [developer.x.com](https://developer.x.com):

```env
X_API_KEY=your_api_key
X_API_SECRET=your_api_secret
X_ACCESS_TOKEN=your_access_token
X_ACCESS_SECRET=your_access_secret
```

### Required: At least one LLM provider

```env
# Pick one (or more):
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434
```

### Required: At least one bot platform

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_token_from_botfather

# Discord
DISCORD_BOT_TOKEN=your_token_from_discord_dev_portal
```

### Optional: Scheduling

```env
# How often to check trends and consider posting (default: 60 min)
CHECK_INTERVAL_MINUTES=60

# Hours during which posting is allowed (24h format, default: 8-22)
POSTING_HOURS_START=8
POSTING_HOURS_END=22

# Minimum trend relevance score to auto-post (0-100, default: 40)
MIN_RELEVANCE_SCORE=40

# Your timezone (default: UTC)
TIMEZONE=America/New_York
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/queue <tweet>` | Add a tweet to the queue |
| `/list` | Show all queued tweets |
| `/remove <id>` | Remove a tweet from the queue |
| `/trends` | Show current trending topics |
| `/analyze` | Run trend analysis now (dry run) |
| `/post` | Force post the best matching tweet now |
| `/status` | Show scheduler status and stats |
| `/help` | Show all commands |

## Docker

```bash
docker build -t trendposter .
docker run -d --env-file .env --name trendposter trendposter
```

Or with Docker Compose:

```bash
docker compose up -d
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐
│  Telegram/Discord│────▶│   Bot Interface   │
│     (user)       │◀────│  (queue mgmt)     │
└─────────────────┘     └────────┬──────────┘
                                 │
                        ┌────────▼──────────┐
                        │   Tweet Queue      │
                        │  (SQLite DB)       │
                        └────────┬──────────┘
                                 │
              ┌──────────────────▼───────────────────┐
              │          Scheduler (cron)              │
              │                                       │
              │  1. Scrape X trending topics           │
              │  2. Load queued tweets                 │
              │  3. LLM: match tweets to trends        │
              │  4. Post best match via X API           │
              │  5. Notify user via bot                 │
              └───────────────────────────────────────┘
```

## LLM Provider Priority

If multiple providers are configured, TrendPoster uses this priority:

1. **Anthropic Claude** (claude-sonnet-4-5-20250929)
2. **OpenAI** (gpt-4o)
3. **Google Gemini** (gemini-2.0-flash)
4. **Ollama** (llama3.2 or configured model)

Override with `LLM_PROVIDER=openai` in your `.env`.

## Contributing

PRs welcome! See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

## License

MIT
