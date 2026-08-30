# Shelfmark Telegram Bot

A Telegram bot for searching and downloading books via your [Shelfmark](https://github.com/calibrain/shelfmark) instance.

## Features

- **Search** books by title, author, or keyword (Shelfmark **Direct** mode – queries the direct-download source)
- **Download** with one-tap confirmation
- **Monitor** download queue status

## Quick Start

### 1. Create a Telegram Bot

Talk to [@BotFather](https://t.me/BotFather) on Telegram and create a new bot. Copy the token.

### 2. Configure & Run

#### With Docker (recommended)

A prebuilt image is published to the GitHub Container Registry on every push to `master`. Save this as `docker-compose.yml`, fill in your values, and run `docker compose up -d`:

```yaml
services:
  shelfmark-bot:
    image: ghcr.io/vjfalk/shelfmark-bot:latest
    container_name: shelfmark-bot
    restart: unless-stopped
    environment:
      TELEGRAM_BOT_TOKEN: ""
      SHELFMARK_URL: ""
      ALLOWED_USER_IDS: ""   # optional, comma-separated
      LOG_LEVEL: "INFO"      # optional
    # Host networking so the bot can reach a Shelfmark on your LAN.
    # Alternatively, put both on the same Docker network.
    network_mode: host
```

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | Token from BotFather |
| `SHELFMARK_URL` | Yes | URL of your Shelfmark instance (e.g. `http://192.168.0.232:8084`) |
| `ALLOWED_USER_IDS` | No | Comma-separated Telegram user IDs to restrict access |
| `LOG_LEVEL` | No | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |

To build from source instead, replace `image:` with `build: .` and run `docker compose up -d --build`.

#### Without Docker

```bash
pip install -r requirements.txt
TELEGRAM_BOT_TOKEN=... SHELFMARK_URL=http://192.168.0.232:8084 python -m bot.main
```

## Usage

| Command | Description |
| --- | --- |
| `/search <query>` | Search for a book |
| `/s <query>` | Short alias for search |
| `/fast <query>` | Download the top result immediately, no picking |
| `/status` | Check download queue |
| `/help` | Show help |

You can also just send a text message with a book title — it behaves like `/fast` and downloads the top result.

### Workflow

1. Send a search query (e.g. `/search Dune`)
2. Tap a result (each result is a downloadable file)
3. Confirm the download
7. Use `/status` to monitor progress

## Architecture

```text
bot/
├── main.py              # Entry point, handler registration
├── config.py            # Environment variable configuration
├── shelfmark_client.py  # Async HTTP client for Shelfmark API
├── utils.py             # Formatting, keyboards, access control
└── handlers/
    ├── search.py        # /search command + plain text search
    ├── book.py          # Book detail view
    ├── releases.py      # Release listing, filtering, download
    └── status.py        # /status command
```

## License

MIT
