"""Telegram bot interface for TrendPoster."""

from __future__ import annotations

import asyncio
import logging

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


class TelegramBot:
    """Telegram bot for managing tweet queue and scheduler."""

    def __init__(self, config: Config, scheduler: Scheduler):
        self.config = config
        self.scheduler = scheduler
        self.queue = scheduler.queue
        self._chat_id: int | None = None

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

    async def _send_notification(self, message: str):
        """Send a notification message to the user."""
        if self._chat_id and self.app.bot:
            await self.app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode="Markdown",
            )

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        self._chat_id = update.effective_chat.id
        await update.message.reply_text(
            "👋 *TrendPoster is running!*\n\n"
            "I'll post your queued tweets when they match trending topics.\n\n"
            "Use /queue <tweet> to add a tweet.\n"
            "Use /help for all commands.",
            parse_mode="Markdown",
        )

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🐦 *TrendPoster Commands*\n\n"
            "/queue <tweet> — Add a tweet to the queue\n"
            "/list — Show all queued tweets\n"
            "/remove <id> — Remove a tweet\n"
            "/trends — Show current trending topics\n"
            "/analyze — Dry run: analyze queue vs trends\n"
            "/post — Force post the best match now\n"
            "/status — Show scheduler status",
            parse_mode="Markdown",
        )

    async def _cmd_queue(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
        self._chat_id = update.effective_chat.id
        await update.message.reply_text("🔍 Fetching trends...")

        trends = await self.scheduler.scraper.get_trends()
        if not trends:
            await update.message.reply_text("❌ Couldn't fetch trends right now.")
            return

        text = self.scheduler.scraper.get_trends_text(trends[:15])
        await update.message.reply_text(f"📈 *Current Trends*\n\n{text}", parse_mode="Markdown")

    async def _cmd_analyze(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        self._chat_id = update.effective_chat.id
        await update.message.reply_text("🔍 Analyzing queue against trends (dry run)...")
        result = await self.scheduler.run_cycle(dry_run=True)
        if result is None:
            await update.message.reply_text(
                "No good matches found right now. "
                "Trends may shift — I'll keep checking."
            )

    async def _cmd_post(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        self._chat_id = update.effective_chat.id
        await update.message.reply_text("🚀 Running post cycle now...")
        result = await self.scheduler.run_cycle(dry_run=False)
        if result is None:
            await update.message.reply_text(
                "No tweet posted — either the queue is empty or nothing matched trends."
            )

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
