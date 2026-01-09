import os
import datetime
import random
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID")
CHANNEL_ID = int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW else None

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is missing. Put DISCORD_TOKEN=... in .env")

TZ = ZoneInfo("America/New_York")  # Timezone

TARGET_WEEKDAY = 2  # Wednesday
TARGET_HOUR = 0     # midnight
TARGET_MINUTE = 0

MESSAGE = "take out the trash @everyone"

TRASH_GIFS = [
    "https://media.giphy.com/media/QuvgjttKi5GL4TPtLB/giphy.gif",
    "https://media.giphy.com/media/tVOlt6mzRFNPuLFL40/giphy.gif",
    "https://media.giphy.com/media/FYXNxV12QG4HspSgOo/giphy.gif",
    "https://media.giphy.com/media/l2Jeg2UYi9opZqxJS/giphy.gif",
    "https://media.giphy.com/media/26ufffLixTAsLgA8g/giphy.gif",
    "https://media.giphy.com/media/11Y9TiZzmEBe25QRSw/giphy.gif",
    "https://media.giphy.com/media/5xaOcLCBzBw4QrtdDP2/giphy.gif",
]

intents = discord.Intents.default()
client = discord.Client(intents=intents)

def next_run(now_local: datetime.datetime) -> datetime.datetime:
    days_ahead = (TARGET_WEEKDAY - now_local.weekday()) % 7
    target = (now_local + datetime.timedelta(days=days_ahead)).replace(
        hour=TARGET_HOUR,
        minute=TARGET_MINUTE,
        second=0,
        microsecond=0,
    )
    if target <= now_local:
        target += datetime.timedelta(days=7)
    return target

def pick_channel(guild: discord.Guild):
    me = guild.me
    if me is None:
        return None

    for ch in guild.text_channels:
        perms = ch.permissions_for(me)
        if perms.send_messages:
            return ch
    return None

@tasks.loop(seconds=30)
async def scheduler():
    now = datetime.datetime.now(TZ)

    if not hasattr(scheduler, "run_at"):
        scheduler.run_at = next_run(now)

    if now >= scheduler.run_at:
        for guild in client.guilds:
            channel = None

            if CHANNEL_ID is not None:
                channel = client.get_channel(CHANNEL_ID)
                if channel is None:
                    print(f"CHANNEL_ID {CHANNEL_ID} not found or not accessible to the bot.")
                    continue
            else:
                channel = pick_channel(guild)

            if channel is None:
                print(f"No postable channel found in guild: {guild.name}")
                continue

            try:
                gif = random.choice(TRASH_GIFS)

                await channel.send(
                    f"{MESSAGE}\n{gif}",
                    allowed_mentions=discord.AllowedMentions(everyone=True),
                )

                print(
                    f"Sent reminder in guild '{guild.name}' "
                    f"channel '{getattr(channel, 'name', 'unknown')}'"
                )
            except Exception as e:
                print(f"Failed to send in guild '{guild.name}': {type(e).__name__}: {e}")

        scheduler.run_at = next_run(now)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    next_time = next_run(datetime.datetime.now(TZ))
    print(f"Next run (local): {next_time.isoformat()}")

    if CHANNEL_ID is not None:
        ch = client.get_channel(CHANNEL_ID)
        if ch is None:
            print(f"Warning: CHANNEL_ID {CHANNEL_ID} not found or not accessible.")
        else:
            print(f"Posting to fixed channel: {getattr(ch, 'name', 'unknown')} ({CHANNEL_ID})")

    if not scheduler.is_running():
        scheduler.start()

client.run(TOKEN)
