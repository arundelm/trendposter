"""Telegram bot interface for TrendPoster."""

from __future__ import annotations

import asyncio
import logging
import time

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from trendposter.config import Config
from trendposter.queue import TweetQueue
from trendposter.scheduler import Scheduler

logger = logging.getLogger(__name__)

# Minimum seconds between expensive operations (LLM calls, posting)
RATE_LIMIT_SECONDS = 30


class TelegramBot:
    """Telegram bot for managing tweet queue and scheduler."""

    def __init__(self, config: Config, scheduler: Scheduler):
        self.config = config
        self.scheduler = scheduler
        self.queue = scheduler.queue
        self._chat_id: int | None = None
        self._last_expensive_call: float = 0.0

        # Find telegram bot config
        tg_config = next(
            (b for b in config.bots if b.platform == "telegram"), None
        )
        if not tg_config:
            raise ValueError("No Telegram bot token configured")

        self.app = Application.builder().token(tg_config.token).build()
        self._register_handlers()

        # Wire up notifications
        scheduler.set_notify_callback(self._send_notification)

    def _is_authorized(self, update: Update) -> bool:
        """Check if the user is allowed to use the bot."""
        if not self.config.allowed_user_ids:
            return True  # No restriction configured
        return update.effective_user.id in self.config.allowed_user_ids

    def _check_rate_limit(self) -> bool:
        """Return True if the rate limit has passed, False if too soon."""
        now = time.monotonic()
        if now - self._last_expensive_call < RATE_LIMIT_SECONDS:
            return False
        self._last_expensive_call = now
        return True

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("help", self._cmd_help))
        self.app.add_handler(CommandHandler("queue", self._cmd_queue))
        self.app.add_handler(CommandHandler("list", self._cmd_list))
        self.app.add_handler(CommandHandler("remove", self._cmd_remove))
        self.app.add_handler(CommandHandler("trends", self._cmd_trends))
        self.app.add_handler(CommandHandler("analyze", self._cmd_analyze))
        self.app.add_handler(CommandHandler("top", self._cmd_top))
        self.app.add_handler(CommandHandler("post", self._cmd_post))
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        # Plain text messages get queued as tweets
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))

    async def _send_notification(self, message: str):
        """Send a notification message to the user."""
        if self._chat_id and self.app.bot:
            await self.app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode="Markdown",
            )

    async def _check_auth(self, update: Update) -> bool:
        """Check auth and send rejection if unauthorized. Returns True if allowed."""
        if self._is_authorized(update):
            return True
        logger.warning(f"Unauthorized access attempt from user {update.effective_user.id}")
        await update.message.reply_text("Unauthorized.")
        return False

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return
        self._chat_id = update.effective_chat.id
        await update.message.reply_text(
            "👋 *TrendPoster is running!*\n\n"
            "I'll post your queued tweets when they match trending topics.\n\n"
            "Use /queue <tweet> to add a tweet.\n"
            "Use /help for all commands.",
            parse_mode="Markdown",
        )

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return
        await update.message.reply_text(
            "🐦 *TrendPoster Commands*\n\n"
            "Just send a message to queue it as a tweet!\n\n"
            "/queue <tweet> — Add a tweet to the queue\n"
            "/list — Show all queued tweets\n"
            "/remove <id> — Remove a tweet\n"
            "/trends — Show current trending topics\n"
            "/analyze — Dry run: analyze queue vs trends\n"
            "/top <N> — Rank top N tweets against trends (default 5)\n"
            "/post <id> — Post a specific tweet by ID\n"
            "/post — Auto-pick and post the best match\n"
            "/status — Show scheduler status",
            parse_mode="Markdown",
        )

    async def _cmd_queue(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return
        self._chat_id = update.effective_chat.id
        text = " ".join(ctx.args) if ctx.args else ""
        if not text:
            await update.message.reply_text("Usage: /queue Your tweet text here")
            return

        if len(text) > 280:
            await update.message.reply_text(
                f"❌ Tweet too long ({len(text)} chars, max 280)"
            )
            return

        if self.queue.queue_size() >= self.config.max_queue_size:
            await update.message.reply_text(
                f"❌ Queue is full ({self.config.max_queue_size} tweets max)"
            )
            return

        tweet = self.queue.add(text)
        await update.message.reply_text(
            f"✅ Queued tweet #{tweet.id}\n"
            f"\"{text}\"\n\n"
            f"📋 {self.queue.queue_size()} tweets in queue"
        )

    async def _cmd_list(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return
        self._chat_id = update.effective_chat.id
        queued = self.queue.list_queued()
        if not queued:
            await update.message.reply_text("📋 Queue is empty. Use /queue to add tweets.")
            return

        lines = ["📋 *Queued Tweets*\n"]
        for t in queued:
            lines.append(f"*#{t.id}* — \"{t.text}\"")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _cmd_remove(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return
        self._chat_id = update.effective_chat.id
        if not ctx.args or not ctx.args[0].isdigit():
            await update.message.reply_text("Usage: /remove <tweet_id>")
            return

        tweet_id = int(ctx.args[0])
        if self.queue.remove(tweet_id):
            await update.message.reply_text(f"🗑️ Removed tweet #{tweet_id}")
        else:
            await update.message.reply_text(f"❌ Tweet #{tweet_id} not found in queue")

    async def _cmd_trends(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return
        self._chat_id = update.effective_chat.id
        await update.message.reply_text("🔍 Fetching trends...")

        trends = await self.scheduler.scraper.get_trends()
        if not trends:
            await update.message.reply_text("❌ Couldn't fetch trends right now.")
            return

        text = self.scheduler.scraper.get_trends_text(trends[:15])
        await update.message.reply_text(f"📈 *Current Trends*\n\n{text}", parse_mode="Markdown")

    async def _cmd_analyze(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return
        self._chat_id = update.effective_chat.id
        if not self._check_rate_limit():
            await update.message.reply_text(f"Please wait {RATE_LIMIT_SECONDS}s between analysis requests.")
            return
        await update.message.reply_text("🔍 Analyzing queue against trends (dry run)...")
        try:
            result = await self.scheduler.run_cycle(dry_run=True)
            if result is None:
                await update.message.reply_text(
                    "No good matches found right now. "
                    "Trends may shift — I'll keep checking."
                )
        except Exception as e:
            logger.error(f"Analyze failed: {e}")
            await update.message.reply_text("Something went wrong during analysis. Check logs.")

    async def _cmd_top(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return
        self._chat_id = update.effective_chat.id
        if not self._check_rate_limit():
            await update.message.reply_text(f"Please wait {RATE_LIMIT_SECONDS}s between analysis requests.")
            return
        limit = 5
        if ctx.args and ctx.args[0].isdigit():
            limit = min(int(ctx.args[0]), 20)

        await update.message.reply_text("🔍 Ranking your tweets against current trends...")

        try:
            rankings = await self.scheduler.rank_cycle(limit=limit)
            if not rankings:
                await update.message.reply_text(
                    "No results — queue may be empty or trends couldn't be fetched."
                )
                return

            lines = [f"📊 *Top {len(rankings)} Tweets*\n"]
            for i, r in enumerate(rankings, 1):
                lines.append(
                    f"*{i}. #{r.tweet_id}* — Score: *{r.relevance_score}/100*\n"
                    f"\"{r.tweet_text}\"\n"
                    f"📈 {r.matched_trend or 'No trend match'}\n"
                    f"💬 {r.reasoning}\n"
                )
            lines.append("Use /post <id> to post a specific tweet.")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Ranking failed: {e}")
            await update.message.reply_text("Something went wrong during ranking. Check logs.")

    async def _cmd_post(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return
        self._chat_id = update.effective_chat.id
        if not self._check_rate_limit():
            await update.message.reply_text(f"Please wait {RATE_LIMIT_SECONDS}s between post requests.")
            return

        # If an ID is provided, post that specific tweet directly
        if ctx.args and ctx.args[0].isdigit():
            tweet_id = int(ctx.args[0])
            await update.message.reply_text(f"🚀 Posting tweet #{tweet_id}...")
            try:
                result = await self.scheduler.post_tweet_by_id(tweet_id)
                if result is None:
                    await update.message.reply_text(
                        f"❌ Tweet #{tweet_id} not found in queue."
                    )
                    return
                await update.message.reply_text(
                    f"✅ *Posted!*\n\n"
                    f"\"{result['text']}\"\n\n"
                    f"🔗 {result['url']}\n\n"
                    f"📋 {self.queue.queue_size()} tweets remaining in queue",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Failed to post tweet #{tweet_id}: {e}")
                await update.message.reply_text("❌ Failed to post tweet. Check logs for details.")
            return

        # No ID — run the full analysis cycle
        await update.message.reply_text("🚀 Running post cycle now...")
        try:
            result = await self.scheduler.run_cycle(dry_run=False)
            if result is None:
                await update.message.reply_text(
                    "No tweet posted — either the queue is empty or nothing matched trends."
                )
        except Exception as e:
            logger.error(f"Post cycle failed: {e}")
            await update.message.reply_text("❌ Something went wrong during posting. Check logs.")

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return
        self._chat_id = update.effective_chat.id
        queue_size = self.queue.queue_size()
        history = self.queue.get_post_history(limit=3)

        status = (
            f"📊 *TrendPoster Status*\n\n"
            f"🤖 LLM: {self.config.llm.provider} ({self.config.llm.model})\n"
            f"📋 Queue: {queue_size} tweets\n"
            f"⏰ Check interval: {self.config.schedule.check_interval_minutes} min\n"
            f"🕐 Posting hours: {self.config.schedule.posting_hours_start}:00 - "
            f"{self.config.schedule.posting_hours_end}:00\n"
            f"📏 Min relevance: {self.config.schedule.min_relevance_score}/100\n"
        )

        if history:
            status += "\n*Recent Posts:*\n"
            for h in history:
                status += f"• \"{h['tweet_text'][:50]}...\" (score: {h['relevance_score']})\n"

        await update.message.reply_text(status, parse_mode="Markdown")

    async def _handle_text(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Queue any plain text message as a tweet."""
        if not self._is_authorized(update):
            return  # Silently ignore unauthorized plain text
        self._chat_id = update.effective_chat.id
        text = update.message.text.strip()
        if not text:
            return

        if len(text) > 280:
            await update.message.reply_text(
                f"❌ Tweet too long ({len(text)} chars, max 280)"
            )
            return

        if self.queue.queue_size() >= self.config.max_queue_size:
            await update.message.reply_text(
                f"❌ Queue is full ({self.config.max_queue_size} tweets max)"
            )
            return

        tweet = self.queue.add(text)
        await update.message.reply_text(
            f"✅ Queued tweet #{tweet.id}\n"
            f"\"{text}\"\n\n"
            f"📋 {self.queue.queue_size()} tweets in queue"
        )

    async def start(self):
        """Start the Telegram bot."""
        logger.info("Starting Telegram bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

    async def stop(self):
        """Stop the Telegram bot."""
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
