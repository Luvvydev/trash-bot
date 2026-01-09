import os
import json
import asyncio
import datetime
import random
import logging
import math
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional, Any

import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID")
CHANNEL_ID = int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW else None

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is missing. Put DISCORD_TOKEN=... in .env")


def _read_int_env(name: str, default: str, lo: int, hi: int) -> int:
    raw = os.getenv(name, default)
    try:
        val = int(raw)
    except ValueError:
        raise SystemExit(f"Invalid {name}: must be an integer, got '{raw}'")
    if not (lo <= val <= hi):
        raise SystemExit(f"Invalid {name}: must be {lo}-{hi}, got {val}")
    return val


def _read_optional_float_env(name: str) -> Optional[float]:
    raw = os.getenv(name)
    if raw is None:
        return None
    try:
        val = float(raw)
    except ValueError:
        raise SystemExit(f"Invalid {name}: must be a number, got '{raw}'")

    if math.isnan(val) or math.isinf(val):
        raise SystemExit(f"Invalid {name}: must be finite, got '{raw}'")

    if val < 0:
        raise SystemExit(f"Invalid {name}: must be >= 0, got '{raw}'")

    return val


TARGET_WEEKDAY = _read_int_env("TARGET_WEEKDAY", "2", 0, 6)  # Monday=0 ... Sunday=6
TARGET_HOUR = _read_int_env("TARGET_HOUR", "0", 0, 23)
TARGET_MINUTE = _read_int_env("TARGET_MINUTE", "0", 0, 59)

TIMEZONE = os.getenv("TIMEZONE", "America/New_York")
try:
    TZ = ZoneInfo(TIMEZONE)
except Exception as e:
    raise SystemExit(f"Invalid TIMEZONE '{TIMEZONE}': {e}")

CATCH_UP = os.getenv("CATCH_UP", "false").strip().lower() in ("1", "true", "yes", "y", "on")
CATCH_UP_MAX_HOURS = _read_optional_float_env("CATCH_UP_MAX_HOURS")
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() in ("1", "true", "yes", "y", "on")

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

if not TRASH_GIFS:
    raise SystemExit("TRASH_GIFS is empty. Add at least one GIF URL.")

STATE_PATH = Path(__file__).with_name("state.json")

LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
if LOG_LEVEL_STR not in LOG_LEVELS:
    raise SystemExit(
        f"Invalid LOG_LEVEL '{LOG_LEVEL_STR}': must be one of {', '.join(sorted(LOG_LEVELS))}"
    )

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL_STR),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("trash_bot")

if DRY_RUN:
    logger.warning("DRY_RUN is enabled: no messages will be sent and state will not be updated")

intents = discord.Intents.default()
client = discord.Client(intents=intents)


def can_mention_everyone_in_channel(channel: Any) -> bool:
    """
    Returns True if this is a guild channel and the bot has mention_everyone permission.
    For DMs or unknown channel types, returns False.

    Note: This can under-report True if member caching is incomplete.
    """
    guild = getattr(channel, "guild", None)
    if guild is None:
        return False

    me = guild.me
    if me is None:
        if client.user is None:
            return False
        me = guild.get_member(client.user.id)
        if me is None:
            return False

    try:
        perms = channel.permissions_for(me)
        return bool(getattr(perms, "mention_everyone", False))
    except Exception:
        return False


def scheduled_run_for_week(now_local: datetime.datetime) -> datetime.datetime:
    """
    Returns the most recent scheduled time (this week) at TARGET_WEEKDAY/TARGET_HOUR/TARGET_MINUTE
    that is <= now_local.
    """
    days_back = (now_local.weekday() - TARGET_WEEKDAY) % 7
    candidate = (now_local - datetime.timedelta(days=days_back)).replace(
        hour=TARGET_HOUR,
        minute=TARGET_MINUTE,
        second=0,
        microsecond=0,
    )
    if candidate > now_local:
        candidate -= datetime.timedelta(days=7)
    return candidate


def next_run_after(now_local: datetime.datetime) -> datetime.datetime:
    """
    Returns the next scheduled run strictly after now_local.
    """
    last = scheduled_run_for_week(now_local)
    nxt = last + datetime.timedelta(days=7)
    if nxt <= now_local:
        nxt += datetime.timedelta(days=7)
    return nxt


def pick_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    me = guild.me
    if me is None:
        return None

    for ch in guild.text_channels:
        perms = ch.permissions_for(me)
        if perms.view_channel and perms.send_messages:
            return ch
    return None


def _load_state() -> dict:
    try:
        if not STATE_PATH.exists():
            return {}
        with STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to load state file: {e}, starting fresh")
        return {}


def _save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True)
            f.write("\n")
        tmp.replace(STATE_PATH)
        logger.debug(f"State saved with {len(state)} entries")
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


def _make_target_key(channel_id: Optional[int], guild_id: Optional[int]) -> str:
    if channel_id is not None:
        return f"channel:{channel_id}"
    if guild_id is not None:
        return f"guild:{guild_id}"
    return "unknown"


def _already_sent_for_run(state: dict, target_key: str, run_at: datetime.datetime) -> bool:
    last = state.get(target_key)
    if not isinstance(last, str) or not last:
        return False
    return last == run_at.isoformat()


async def _resolve_fixed_channel() -> discord.abc.Messageable:
    if CHANNEL_ID is None:
        raise RuntimeError("CHANNEL_ID is not set")

    ch = client.get_channel(CHANNEL_ID)
    if ch is not None:
        return ch

    try:
        fetched = await client.fetch_channel(CHANNEL_ID)
        return fetched
    except discord.NotFound:
        raise SystemExit(f"CHANNEL_ID {CHANNEL_ID} not found.")
    except discord.Forbidden:
        raise SystemExit(f"CHANNEL_ID {CHANNEL_ID} is not accessible (missing permissions).")
    except discord.HTTPException as e:
        raise SystemExit(f"Failed to fetch CHANNEL_ID {CHANNEL_ID}: {type(e).__name__}: {e}")


async def _sleep_until(target: datetime.datetime) -> None:
    """
    Sleep until target time, robust against early wakeups and clock shifts.
    asyncio.sleep is cancellable; cancellation will propagate cleanly.
    """
    while True:
        now = datetime.datetime.now(TZ)
        remaining = (target - now).total_seconds()
        if remaining <= 0:
            if remaining < -60:
                logger.warning(f"Clock jump detected: {abs(remaining):.0f}s behind schedule")
            return
        await asyncio.sleep(min(60.0, remaining))


async def _send_once(channel: discord.abc.Messageable) -> None:
    can_mention = can_mention_everyone_in_channel(channel)
    message_text = MESSAGE if can_mention else MESSAGE.replace("@everyone", "").strip()

    if not can_mention and "@everyone" in MESSAGE:
        ch_id = getattr(channel, "id", None)
        logger.warning(f"Cannot mention @everyone in channel {ch_id}, sending without ping")

    gif = random.choice(TRASH_GIFS)

    if DRY_RUN:
        ch_name = getattr(channel, "name", f"ID:{getattr(channel, 'id', 'unknown')}")
        logger.info(f"[DRY RUN] Would send to {ch_name}: {message_text}\n{gif}")
        return

    await channel.send(
        f"{message_text}\n{gif}",
        allowed_mentions=discord.AllowedMentions(everyone=can_mention),
    )


async def _run_send_window(state: dict, scheduled_at: datetime.datetime) -> None:
    """
    Send reminders for the given scheduled time, deduped by state.json.
    """
    try:
        if CHANNEL_ID is not None:
            channel = await _resolve_fixed_channel()
            target_key = _make_target_key(CHANNEL_ID, None)

            if _already_sent_for_run(state, target_key, scheduled_at):
                logger.info(f"Already sent for {target_key} at {scheduled_at.isoformat()}, skipping.")
                return

            await _send_once(channel)

            if not DRY_RUN:
                state[target_key] = scheduled_at.isoformat()
                _save_state(state)
                logger.info(f"Sent reminder to fixed channel {CHANNEL_ID} for {scheduled_at.isoformat()}")
            else:
                logger.info(f"[DRY RUN] Would update state for {target_key} at {scheduled_at.isoformat()}")
            return

        for guild in client.guilds:
            channel = pick_channel(guild)
            if channel is None:
                logger.warning(f"No postable channel found in guild: {guild.name} (ID: {guild.id})")
                continue

            target_key = _make_target_key(None, guild.id)
            if _already_sent_for_run(state, target_key, scheduled_at):
                logger.info(
                    f"Already sent for guild '{guild.name}' (ID: {guild.id}) at {scheduled_at.isoformat()}, skipping."
                )
                continue

            try:
                await _send_once(channel)

                if not DRY_RUN:
                    state[target_key] = scheduled_at.isoformat()
                    _save_state(state)
                    logger.info(
                        f"Sent reminder in guild '{guild.name}' (ID: {guild.id}) "
                        f"channel '{getattr(channel, 'name', 'unknown')}' (ID: {getattr(channel, 'id', 'unknown')}) "
                        f"for {scheduled_at.isoformat()}"
                    )
                else:
                    logger.info(
                        f"[DRY RUN] Would update state for guild '{guild.name}' (ID: {guild.id}) "
                        f"at {scheduled_at.isoformat()}"
                    )
            except discord.Forbidden:
                logger.error(f"Forbidden: cannot send in guild '{guild.name}' (ID: {guild.id}).")
            except discord.HTTPException as e:
                logger.error(
                    f"HTTP error sending in guild '{guild.name}' (ID: {guild.id}): {type(e).__name__}: {e}"
                )
            except Exception as e:
                logger.error(f"Failed to send in guild '{guild.name}' (ID: {guild.id}): {type(e).__name__}: {e}")

    except SystemExit as e:
        logger.critical(str(e))
        await client.close()
        return
    except Exception:
        logger.exception("Error during send window")


async def schedule_loop():
    state = _load_state()
    logger.info(
        f"Starting scheduler: weekday={TARGET_WEEKDAY}, time={TARGET_HOUR:02d}:{TARGET_MINUTE:02d}, "
        f"tz={TIMEZONE}, catch_up={CATCH_UP}, "
        f"catch_up_max_hours={CATCH_UP_MAX_HOURS if CATCH_UP_MAX_HOURS is not None else 'unlimited'}"
    )

    try:
        while not client.is_closed():
            now = datetime.datetime.now(TZ)
            last_scheduled = scheduled_run_for_week(now)
            next_scheduled = next_run_after(now)

            if CATCH_UP:
                hours_since_last = (now - last_scheduled).total_seconds() / 3600.0
                if CATCH_UP_MAX_HOURS is None or hours_since_last <= CATCH_UP_MAX_HOURS:
                    await _run_send_window(state, last_scheduled)
                    now = datetime.datetime.now(TZ)
                    next_scheduled = next_run_after(now)
                else:
                    logger.debug(
                        f"Skipping catch-up: last scheduled was {hours_since_last:.1f}h ago "
                        f"(max={CATCH_UP_MAX_HOURS}h)"
                    )

            logger.info(f"Next run: {next_scheduled.isoformat()}")
            await _sleep_until(next_scheduled)

            await _run_send_window(state, next_scheduled)

            await asyncio.sleep(1)

    except asyncio.CancelledError:
        logger.info("Scheduler task cancelled")
        raise
    except Exception:
        logger.exception("Scheduler crashed")
        await client.close()


@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (ID: {getattr(client.user, 'id', 'unknown')})")

    if CHANNEL_ID is not None:
        try:
            ch = await _resolve_fixed_channel()
            logger.info(
                f"Posting to fixed channel: {getattr(ch, 'name', 'unknown')} (ID: {CHANNEL_ID}), "
                f"type={type(ch).__name__}"
            )
        except SystemExit as e:
            logger.critical(str(e))
            await client.close()
            return

    if not hasattr(client, "_schedule_task"):
        client._schedule_task = asyncio.create_task(schedule_loop())


try:
    client.run(TOKEN)
except KeyboardInterrupt:
    logger.info("Bot stopped by user")
except Exception as e:
    logger.critical(f"Bot failed to start: {type(e).__name__}: {e}")
