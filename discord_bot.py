"""Discord bot interface for TrendPoster."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from trendposter.config import Config
from trendposter.scheduler import Scheduler

logger = logging.getLogger(__name__)


class DiscordBot:
    """Discord bot for managing tweet queue and scheduler."""

    def __init__(self, config: Config, scheduler: Scheduler):
        self.config = config
        self.scheduler = scheduler
        self.queue = scheduler.queue
        self._channel_id: int | None = None

        dc_config = next(
            (b for b in config.bots if b.platform == "discord"), None
        )
        if not dc_config:
            raise ValueError("No Discord bot token configured")

        self.token = dc_config.token
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self._register_commands()

        scheduler.set_notify_callback(self._send_notification)

    async def _send_notification(self, message: str):
        if self._channel_id:
            channel = self.bot.get_channel(self._channel_id)
            if channel:
                await channel.send(message)

    def _register_commands(self):
        bot = self.bot

        @bot.command(name="queue")
        async def cmd_queue(ctx: commands.Context, *, text: str = ""):
            self._channel_id = ctx.channel.id
            if not text:
                await ctx.send("Usage: `!queue Your tweet text here`")
                return
            if len(text) > 280:
                await ctx.send(f"❌ Tweet too long ({len(text)} chars, max 280)")
                return
            if self.queue.queue_size() >= self.config.max_queue_size:
                await ctx.send(f"❌ Queue full ({self.config.max_queue_size} max)")
                return
            tweet = self.queue.add(text)
            await ctx.send(
                f"✅ Queued tweet #{tweet.id}\n"
                f"> {text}\n"
                f"📋 {self.queue.queue_size()} tweets in queue"
            )

        @bot.command(name="list")
        async def cmd_list(ctx: commands.Context):
            self._channel_id = ctx.channel.id
            queued = self.queue.list_queued()
            if not queued:
                await ctx.send("📋 Queue is empty. Use `!queue` to add tweets.")
                return
            lines = ["📋 **Queued Tweets**\n"]
            for t in queued:
                lines.append(f"**#{t.id}** — \"{t.text}\"")
            await ctx.send("\n".join(lines))

        @bot.command(name="remove")
        async def cmd_remove(ctx: commands.Context, tweet_id: int = 0):
            self._channel_id = ctx.channel.id
            if not tweet_id:
                await ctx.send("Usage: `!remove <tweet_id>`")
                return
            if self.queue.remove(tweet_id):
                await ctx.send(f"🗑️ Removed tweet #{tweet_id}")
            else:
                await ctx.send(f"❌ Tweet #{tweet_id} not found")

        @bot.command(name="trends")
        async def cmd_trends(ctx: commands.Context):
            self._channel_id = ctx.channel.id
            await ctx.send("🔍 Fetching trends...")
            trends = await self.scheduler.scraper.get_trends()
            if not trends:
                await ctx.send("❌ Couldn't fetch trends.")
                return
            text = self.scheduler.scraper.get_trends_text(trends[:15])
            await ctx.send(f"📈 **Current Trends**\n\n{text}")

        @bot.command(name="analyze")
        async def cmd_analyze(ctx: commands.Context):
            self._channel_id = ctx.channel.id
            await ctx.send("🔍 Analyzing (dry run)...")
            result = await self.scheduler.run_cycle(dry_run=True)
            if result is None:
                await ctx.send("No good matches right now.")

        @bot.command(name="post")
        async def cmd_post(ctx: commands.Context):
            self._channel_id = ctx.channel.id
            await ctx.send("🚀 Running post cycle...")
            result = await self.scheduler.run_cycle(dry_run=False)
            if result is None:
                await ctx.send("No tweet posted.")

        @bot.command(name="status")
        async def cmd_status(ctx: commands.Context):
            self._channel_id = ctx.channel.id
            queue_size = self.queue.queue_size()
            await ctx.send(
                f"📊 **TrendPoster Status**\n\n"
                f"🤖 LLM: {self.config.llm.provider} ({self.config.llm.model})\n"
                f"📋 Queue: {queue_size} tweets\n"
                f"⏰ Interval: {self.config.schedule.check_interval_minutes} min\n"
                f"📏 Min score: {self.config.schedule.min_relevance_score}/100"
            )

    async def start(self):
        logger.info("Starting Discord bot...")
        await self.bot.start(self.token)

    async def stop(self):
        await self.bot.close()
