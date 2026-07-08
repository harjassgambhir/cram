# CRAM-1 Telegram Bot

Exposes CRAM-1 to doctors via Telegram. No terminal required — doctors send a clinical scenario, receive a PDF report, and ask follow-up questions in chat.

## How it works

1. Doctor sends a scenario to the bot
2. Bot acknowledges immediately and starts research in the background
3. After ~15 minutes, bot sends a summary + PDF report
4. Doctor can ask follow-up questions — answered from the session evidence
5. `/new` starts a fresh research question

## Setup

### 1. Get a Telegram Bot Token

1. Open Telegram, search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the token (looks like `123456:ABCdef...`)

### 2. Configure

```bash
cp bot/.env.example bot/.env
# Edit bot/.env and fill in TELEGRAM_BOT_TOKEN and OPENROUTER_API_KEY
```

### 3. Install dependencies

```bash
pip install -r bot/requirements.txt
```

Or if using uv (recommended):
```bash
uv pip install -r bot/requirements.txt
```

### 4. Run

**On your laptop (testing):**
```bash
# Keep laptop awake and run the bot
caffeinate -s python -m bot.main
```

**In the background:**
```bash
nohup python -m bot.main > bot/bot.log 2>&1 &
tail -f bot/bot.log   # watch logs
```

**On a VPS (production):**

Create `/etc/systemd/system/cram-bot.service`:
```ini
[Unit]
Description=CRAM-1 Telegram Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/cram
ExecStart=/home/ubuntu/cram/.venv/bin/python -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable cram-bot
sudo systemctl start cram-bot
sudo journalctl -u cram-bot -f   # watch logs
```

## Bot Commands

| Command | Description |
|---------|-------------|
| Send any text | Start research on that scenario |
| `/new` | Clear session, start fresh |
| `/cancel` | Stop current research run |
| `/history` | List past research sessions |
| `/help` | Show welcome message |

## Multi-user

Each Telegram user gets their own isolated session. Multiple doctors can use the bot simultaneously — each research run is in its own thread.

## Costs

Each research run costs approximately $0.03–0.10 USD in API fees (OpenRouter).

## PDF generation

PDF export is enabled by default for the bot. Requires `weasyprint`:
```bash
pip install markdown weasyprint
```

If weasyprint is not installed, the bot falls back to sending the markdown file.
