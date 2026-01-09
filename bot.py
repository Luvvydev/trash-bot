import os
import json
import asyncio
import datetime
import random
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID")
CHANNEL_ID = int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW else None

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is missing. Put DISCORD_TOKEN=... in .env")

TZ = ZoneInfo("America/New_York")  # Timezone

TARGET_WEEKDAY = 2  # Wednesday (Mon=0 ... Sun=6)
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

STATE_PATH = Path(__file__).with_name("state.json")

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

def _load_state() -> dict:
    try:
        if not STATE_PATH.exists():
            return {}
        with STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(STATE_PATH)

def _make_target_key(channel_id: int | None, guild_id: int | None) -> str:
    if channel_id is not None:
        return f"channel:{channel_id}"
    if guild_id is not None:
        return f"guild:{guild_id}"
    return "unknown"

def _already_sent_for_run(state: dict, target_key: str, run_at: datetime.datetime) -> bool:
    last = state.get(target_key)
    if not isinstance(last, str) or not last:
        return False

    # If last sent timestamp matches this scheduled run timestamp, treat as already sent.
    # This prevents duplicates across restarts during the same scheduled window.
    return last == run_at.isoformat()

async def _resolve_fixed_channel() -> discord.abc.Messageable:
    if CHANNEL_ID is None:
        raise RuntimeError("CHANNEL_ID is not set")

    ch = client.get_channel(CHANNEL_ID)
    if ch is not None:
        return ch

    # Fallback to API fetch in case the channel is not cached yet.
    try:
        fetched = await client.fetch_channel(CHANNEL_ID)
        return fetched
    except discord.NotFound:
        raise SystemExit(f"CHANNEL_ID {CHANNEL_ID} not found.")
    except discord.Forbidden:
        raise SystemExit(f"CHANNEL_ID {CHANNEL_ID} is not accessible (missing permissions).")
    except discord.HTTPException as e:
        raise SystemExit(f"Failed to fetch CHANNEL_ID {CHANNEL_ID}: {type(e).__name__}: {e}")

async def schedule_loop():
    state = _load_state()

    while not client.is_closed():
        now = datetime.datetime.now(TZ)
        run_at = next_run(now)

        seconds = (run_at - now).total_seconds()
        if seconds > 0:
            print(f"Next run (local): {run_at.isoformat()}")
            await asyncio.sleep(seconds)

        # Recompute after sleep to avoid drift and handle time changes.
        now = datetime.datetime.now(TZ)
        run_at = next_run(now)

        # If we woke up late, we still treat this run_at as the intended window.
        # Only send once per target_key per run_at.
        try:
            if CHANNEL_ID is not None:
                channel = await _resolve_fixed_channel()
                target_key = _make_target_key(CHANNEL_ID, None)

                if _already_sent_for_run(state, target_key, run_at):
                    print(f"Already sent for {target_key} at {run_at.isoformat()}, skipping.")
                else:
                    gif = random.choice(TRASH_GIFS)
                    await channel.send(
                        f"{MESSAGE}\n{gif}",
                        allowed_mentions=discord.AllowedMentions(everyone=True),
                    )
                    state[target_key] = run_at.isoformat()
                    _save_state(state)
                    print(f"Sent reminder to fixed channel ({CHANNEL_ID}).")
            else:
                for guild in client.guilds:
                    channel = pick_channel(guild)
                    if channel is None:
                        print(f"No postable channel found in guild: {guild.name}")
                        continue

                    target_key = _make_target_key(None, guild.id)
                    if _already_sent_for_run(state, target_key, run_at):
                        print(f"Already sent for {guild.name} at {run_at.isoformat()}, skipping.")
                        continue

                    try:
                        gif = random.choice(TRASH_GIFS)
                        await channel.send(
                            f"{MESSAGE}\n{gif}",
                            allowed_mentions=discord.AllowedMentions(everyone=True),
                        )
                        state[target_key] = run_at.isoformat()
                        _save_state(state)
                        print(
                            f"Sent reminder in guild '{guild.name}' "
                            f"channel '{getattr(channel, 'name', 'unknown')}'"
                        )
                    except discord.Forbidden:
                        print(f"Forbidden: cannot send in guild '{guild.name}'.")
                    except discord.HTTPException as e:
                        print(f"HTTP error sending in guild '{guild.name}': {type(e).__name__}: {e}")
                    except Exception as e:
                        print(f"Failed to send in guild '{guild.name}': {type(e).__name__}: {e}")

        except SystemExit as e:
            # Hard fail for invalid fixed channel configuration.
            print(str(e))
            await client.close()
            return
        except Exception as e:
            print(f"Scheduler error: {type(e).__name__}: {e}")

        # Ensure we do not immediately re-run if the clock is weird.
        await asyncio.sleep(1)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    if CHANNEL_ID is not None:
        try:
            ch = await _resolve_fixed_channel()
            print(f"Posting to fixed channel: {getattr(ch, 'name', 'unknown')} ({CHANNEL_ID})")
        except SystemExit as e:
            print(str(e))
            await client.close()
            return

    if not hasattr(client, "_schedule_task"):
        client._schedule_task = asyncio.create_task(schedule_loop())

client.run(TOKEN)
