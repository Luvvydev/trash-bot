# TrashBot

A minimal for personal use Discord bot that sends a weekly `@everyone` reminder to take out the trash.

---

## Features

- Sends a reminder every **Wednesday at 12:00 AM**
- Uses **America/New_York** timezone (Eastern Time)
- Posts to a **fixed, configured channel**
- Uses `@everyone` to ensure visibility
- Configuration and secrets stored safely in `.env`

---

## Requirements

- Python 3.10+
- A Discord server where you can add bots
- Bot permissions:
  - Send Messages
  - Read Message History
  - Mention @everyone

---

## Setup

### 1) Clone the repository

```bash
git clone https://github.com/Luvvydev/trash-bot.git
cd trash-bot
```

---

### 2) Create and activate a virtual environment

Create the virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Your terminal prompt should show:

```text
(.venv)
```

---

### 3) Install dependencies

```bash
python -m pip install -U pip
python -m pip install discord.py python-dotenv
```

---

## Configuration

Create a file named `.env` in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token_here
CHANNEL_ID=123456789012345678
```

---

### Getting `DISCORD_TOKEN`

1. Open **Discord Developer Portal**
2. Select **Your Application**
3. Go to **Bot**
4. Click **Reset Token** (if needed)
5. Copy the bot token

---

### Getting `CHANNEL_ID`

1. Open **Discord User Settings**
2. Go to **Advanced**
3. Enable **Developer Mode**
4. Right-click the channel you want
5. Click **Copy ID**

---

## Add the Bot to Your Server

In **Discord Developer Portal**:

1. Go to **OAuth2**
2. Open **URL Generator**
3. Under **Scopes**, select:
   - `bot`
4. Under **Bot Permissions**, select:
   - Send Messages
   - Read Message History
   - Mention Everyone
5. Copy the **Generated URL**
6. Open it in your browser
7. Select your server
8. Click **Authorize**

If your server does not appear, you do not have **Manage Server** permission.

---

## Run the Bot

```bash
python bot.py
```

Expected startup output:

```text
Logged in as TrashBot#4663
Next run (local): 2026-01-14T00:00:00-05:00
Posting to fixed channel: trash-reminders-wednesday (1458981074288902349)
```

---

## Scheduling

- **Timezone:** America/New_York
- **Schedule:** Wednesday at 12:00 AM

### Notes

- The bot must be running at the scheduled time
- If the bot is offline, the reminder will not send

---

## Permissions Checklist for `@everyone`

If the bot posts but does not ping:

### Server Role Permissions

1. Server Settings → Roles → **TrashBot**
2. Enable:
   - Mention `@everyone`
   - Mention `@here`
   - Mention All Roles

### Channel Permissions

1. Channel Settings → Permissions
2. Ensure **TrashBot** can:
   - View Channel
   - Send Messages
   - Mention Everyone

Both role permissions and channel overrides must allow mentions.

---

## Troubleshooting

### Error: expected token to be a str, received NoneType

- `.env` is missing `DISCORD_TOKEN=...`
- `.env` is not in the same folder as `bot.py`
- Formatting must be `KEY=VALUE`

### Bot is online but does not post

- Bot is not running continuously
- `CHANNEL_ID` is incorrect
- Bot lacks channel permissions

### Bot posts but does not ping

- Permission issue
- Review the permissions checklist above

---

## Security

- Never commit `.env`
- Never paste your bot token publicly
- Reset the token immediately if exposed

---

## Deployment Notes

For reliable reminders, the bot must run 24/7.

Options:

- Always-on home machine
- VPS
- Raspberry Pi
- Docker on a server

If the terminal closes or the computer sleeps, the bot stops.

---

## Development

### Update dependencies

```bash
python -m pip install -U discord.py python-dotenv
```

### Commit changes

```bash
git add -A
git commit -m "Describe your change"
git push
```

---

## License

MIT
