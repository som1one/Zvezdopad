import asyncio
import asyncpg
import time
import logging
import random
from datetime import datetime, timedelta, time as dt_time, timezone
from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import BotBlocked, ChatNotFound, UserDeactivated, TelegramAPIError, InvalidQueryID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import Client

import database
from handlers.api import active_spins, SPIN_TIMEOUT_SECONDS

from settings import (
    ADMIN_IDS, LINK_BOT, AVAILABLE_DAILY_GIFTS, DEFAULT_DAILY_GIFT_KEY,
    MIN_GIFT, MAX_GIFT, MIN_GIFT_L, MAX_GIFT_L,
    MIN_REF_REWARD, MAX_REF_REWARD, MIN_REF_REWARD_X2, MAX_REF_REWARD_X2,
    CLICK_MIN_REWARD, CLICK_MAX_REWARD, CLICK_MIN_REWARD_X2, CLICK_MAX_REWARD_X2
)
from utils import t, send_gift_with_retry

log = logging.getLogger('scheduler')


async def update_rewards():
    now_utc = datetime.now(timezone.utc)
    hour_utc = now_utc.hour
    is_lucky = 9 <= hour_utc < 10

    pool = database.db_pool
    if not pool: log.error("DB pool not initialized for rewards update!"); return

    async with pool.acquire() as conn:
        try:
            current_lucky_status = await conn.fetchval(
                "SELECT value FROM config WHERE key='is_lucky_time'") or '0'

            async with conn.transaction():
                if is_lucky and current_lucky_status == '0':
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(MIN_GIFT_L), 'min_gift')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(MAX_GIFT_L), 'max_gift')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(MIN_REF_REWARD_X2),
                                       'min_ref_reward')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(MAX_REF_REWARD_X2),
                                       'max_ref_reward')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(CLICK_MIN_REWARD_X2),
                                       'click_min_reward')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(CLICK_MAX_REWARD_X2),
                                       'click_max_reward')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", '1', 'is_lucky_time')
                    log.info("LUCKY HOUR ACTIVE! Rewards updated.")
                elif not is_lucky and current_lucky_status == '1':
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(MIN_GIFT), 'min_gift')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(MAX_GIFT), 'max_gift')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(MIN_REF_REWARD), 'min_ref_reward')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(MAX_REF_REWARD), 'max_ref_reward')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(CLICK_MIN_REWARD),
                                       'click_min_reward')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", str(CLICK_MAX_REWARD),
                                       'click_max_reward')
                    await conn.execute("UPDATE config SET value=$1 WHERE key=$2", '0', 'is_lucky_time')
                    log.info("Lucky hour ended. Reverted rewards.")
                else:
                    log.debug(f"Reward status remains {'LUCKY' if is_lucky else 'REGULAR'}.")
        except asyncpg.PostgresError as e:
            log.exception(f"DB error during reward update: {e}")
        except Exception as e:
            log.exception(f"Unexpected error reward update: {e}")


async def send_reminder(bot: Bot, user_id: int, days_inactive: int):
    if days_inactive == 1:
        messages = [("Эй! Ты куда пропал?", "Ну ладно, посмотрю 🌟"), ("Привет! Скорее к нам!", "Я в деле 🚀"),
                    ("Хей! Пора возвращаться!", "Ну да, точно я 💪")]
    elif days_inactive >= 7:
        messages = [("Неделя без тебя! Давай в бот.", "Захожу, что делать? ✨"),
                    ("Звёзды скучали. Ты где?", "Вернулся! Что нового? 🌟")]
    elif days_inactive >= 3:
        messages = [("Три дня? Серьёзно? К заданиям!", "Да-да, иду 🌟"),
                    ("Эх, три дня без звёзд… Возвращайся!", "Вот он я 🌟")]
    else:
        return False

    message_text, button_text = random.choice(messages)
    keyboard = InlineKeyboardMarkup(row_width=1)
    button = InlineKeyboardButton(text=button_text, url=LINK_BOT)
    keyboard.add(button)

    try:
        await bot.send_message(user_id, message_text, reply_markup=keyboard)
        log.info(f"Reminder sent to inactive user {user_id} ({days_inactive} days)")
        return True
    except (BotBlocked, UserDeactivated, ChatNotFound) as e:
        log.warning(f"Cannot send reminder to {user_id}: {e}. Deleting.")
        await database.delete_user(user_id)
        return False
    except TelegramAPIError as e:
        log.error(f"Failed send reminder to {user_id}: {e}");
        return False
    except Exception as e:
        log.exception(f"Unexpected error sending reminder to {user_id}: {e}");
        return False


async def check_inactive_users_task(bot: Bot):
    log.info("Starting inactive user check...")
    inactive_days_thresholds = [7, 3, 1]
    sent_users = set()
    deleted_count = 0;
    sent_count = 0
    start_time = time.time()

    for days in inactive_days_thresholds:
        try:
            inactive_user_ids = await database.get_inactive_users(days)
            log.info(f"Checking users inactive >= {days} days. Found: {len(inactive_user_ids)}")
            for user_id in inactive_user_ids:
                if user_id not in sent_users:
                    sent_status = await send_reminder(bot, user_id, days)
                    if sent_status:
                        sent_users.add(user_id);
                        sent_count += 1
                    else:
                        exists = await database.user_exists(user_id)
                        if not exists: deleted_count += 1
                    await asyncio.sleep(0.06)
        except Exception as e:
            log.exception(f"Error processing inactive users {days} days threshold:")

    duration = time.time() - start_time
    summary = (
        f"<b>✅ Проверка неактивных завершена!</b> ({duration:.1f} сек)\n\n✉️ Отправлено: {sent_count}\n🗑 Удалено: {deleted_count}")
    log.info(f"Inactive check finished. Sent: {sent_count}, Deleted: {deleted_count}, Duration: {duration:.2f}s")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, summary, parse_mode="HTML")
        except Exception as e:
            log.error(f"Failed send summary to admin {admin_id}: {e}")


async def check_channels_for_deletion_task():
    log.debug("Starting check channels pending deletion...")
    now_utc = datetime.now(timezone.utc)
    channels_to_delete_now = []
    pool = database.db_pool
    if not pool: log.error("DB pool not initialized for channel deletion check!"); return

    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                "SELECT channel_id FROM channels WHERE delete_time IS NOT NULL AND delete_time <= $1",
                now_utc
            )
            channels_to_delete_now = [row['channel_id'] for row in rows]
        except asyncpg.PostgresError as db_err:
            log.error(f"DB error checking channels for deletion: {db_err}");
            return

    if channels_to_delete_now:
        log.info(f"Found {len(channels_to_delete_now)} channels scheduled for deletion: {channels_to_delete_now}")
        deleted_count, failed_count = 0, 0
        for channel_id in channels_to_delete_now:
            try:
                deleted = await database.delete_channel_db(channel_id)
                if deleted:
                    log.info(f"Channel {channel_id} deleted.");
                    deleted_count += 1
                else:
                    log.warning(f"Channel {channel_id} scheduled but not found.");
                    failed_count += 1
            except Exception as e:
                log.exception(f"Error deleting channel {channel_id}:");
                failed_count += 1
        log.info(f"Channel deletion finished. Deleted: {deleted_count}, Failed/Not Found: {failed_count}")
    else:
        log.debug("No channels found pending deletion.")


async def daily_top_referrer_award_task(bot: Bot, app: Client | None):
    log.info("Executing daily top referrer award task...")
    if not app: log.warning("Pyrogram client (app) unavailable. Skipping daily award."); return

    try:
        selected_gift_id = await database.get_selected_daily_gift()
        if selected_gift_id is None: log.warning("No daily gift selected. Skipping award."); return

        selected_gift_name = "Неизвестный подарок";
        selected_gift_cost = 0
        for name, gift_id_in_dict in AVAILABLE_DAILY_GIFTS.items():
            if gift_id_in_dict == selected_gift_id:
                selected_gift_name = name.split("(")[0].strip()
                try:
                    cost_str = name.split("(")[1].replace(")", "").replace("⭐", "");
                    selected_gift_cost = int(cost_str)
                except:
                    log.warning(f"Could not parse cost from gift name: {name}");
                    selected_gift_cost = 0
                break

        top_referrers = await database.get_referral_top_by_period('day')
        if not top_referrers: log.info("No referrers found last 24h. Skipping award."); return

        top_user_data = top_referrers[0]
        winner_id = top_user_data['referral_id'];
        ref_count = top_user_data['ref_count']

        if winner_id and ref_count > 0:
            log.info(f"Top referrer past day: User {winner_id} with {ref_count} referrals.")
            try:
                log.info(f"Attempting send gift {selected_gift_id} ({selected_gift_name}) to winner {winner_id}...")
                await send_gift_with_retry(app, winner_id, selected_gift_id, bot_instance=bot)
                log.info(f"Successfully sent daily award (gift_id: {selected_gift_id}) to user {winner_id}.")
                try:
                    await bot.send_message(winner_id,
                                           f"🎉 Топ-1 рефовод дня ({ref_count} реф.)!\n🎁 Награда: '{selected_gift_name}' ({selected_gift_cost}⭐).")
                except Exception as notify_err:
                    log.error(f"Failed notify daily award winner {winner_id}: {notify_err}")
            except Exception as gift_err:
                log.error(f"Failed send daily gift {selected_gift_id} to user {winner_id}: {gift_err}")
        else:
            log.info("Top referrer invalid or zero refs. Skipping award.")
    except Exception as e:
        log.exception(f"Error during daily top referrer award: {e}")


async def cleanup_abandoned_spins(bot: Bot):
    now = time.time()
    processed_spins, auto_sold_count, forfeited_count = 0, 0, 0
    spins_to_remove = []
    current_spin_ids = list(active_spins.keys())

    if not current_spin_ids: log.debug("No active spins for cleanup."); return
    log.info(f"Starting abandoned spin cleanup. Active: {len(current_spin_ids)}")

    for spin_id in current_spin_ids:
        if spin_id not in active_spins: continue
        spin_data = active_spins.get(spin_id)
        if not spin_data: log.warning(f"Spin data {spin_id} disappeared."); continue

        user_id, timestamp, prize_data = spin_data.get("user_id"), spin_data.get("timestamp"), spin_data.get("prize")
        if not all([user_id, timestamp, prize_data]):
            log.warning(f"Invalid spin data {spin_id}. Removing.");
            spins_to_remove.append(spin_id);
            continue

        if now - timestamp > SPIN_TIMEOUT_SECONDS:
            processed_spins += 1
            log.info(f"Spin {spin_id} user {user_id} timed out. Processing...")
            can_sell, prize_cost, prize_name, prize_emoji = prize_data.get("canSell", False), float(
                prize_data.get("costNumber", 0)), prize_data.get("name", "Неизвестный приз"), prize_data.get("emoji",
                                                                                                             "❓")

            if can_sell and prize_cost > 0:
                try:
                    await database.add_stars(user_id, prize_cost)
                    auto_sold_count += 1
                    log.info(f"Auto-sold '{prize_name}' ({prize_cost} stars) user {user_id} spin {spin_id}.")
                    try:
                        await bot.send_message(user_id,
                                               f"⏳ Приз {prize_emoji} ({escape(prize_name)}) не забран вовремя. Авто-продажа: +{prize_cost:.0f} ⭐.")
                    except Exception as notify_err:
                        log.warning(f"Could not notify user {user_id} auto-sold: {notify_err}")
                except Exception as db_err:
                    log.exception(
                        f"DB error auto-sell user {user_id}, spin {spin_id}: {db_err}");
                    continue
            else:
                forfeited_count += 1
                log.info(f"Prize '{prize_name}' user {user_id} forfeited spin {spin_id}.")
                try:
                    await bot.send_message(user_id,
                                           f"⏳ Приз {prize_emoji} ({escape(prize_name)}) не забран вовремя и сгорел.")
                except Exception as notify_err:
                    log.warning(f"Could not notify user {user_id} forfeited: {notify_err}")
            spins_to_remove.append(spin_id)

    removed_count = 0
    for spin_id in spins_to_remove:
        if spin_id in active_spins:
            try:
                del active_spins[spin_id];
                removed_count += 1
            except KeyError:
                pass
    if processed_spins > 0: log.info(
        f"Abandoned spin cleanup finished. Processed: {processed_spins}, Sold: {auto_sold_count}, Forfeited: {forfeited_count}, Removed: {removed_count}")


def setup_scheduler(bot: Bot, client: Client | None = None):
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(update_rewards, 'cron', hour='*', minute='0', id='update_rewards', replace_existing=True)
    scheduler.add_job(check_inactive_users_task, 'cron', hour='3', minute='5', args=[bot], id='inactive_user_check',
                      replace_existing=True)
    scheduler.add_job(check_channels_for_deletion_task, 'interval', minutes=5, id='channel_deletion_check',
                      replace_existing=True)
    scheduler.add_job(daily_top_referrer_award_task, 'cron', hour='0', minute='1', args=[bot, client],
                      id='daily_top_award', replace_existing=True)
    scheduler.add_job(cleanup_abandoned_spins, 'interval', minutes=2, args=[bot], id='abandoned_spin_cleanup',
                      replace_existing=True)

    log.info("Starting APScheduler...")
    try:
        scheduler.start();
        log.info("APScheduler started successfully.")
    except Exception as e:
        log.exception(f"Failed to start APScheduler: {e}")
