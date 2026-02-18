"""CLI entrypoint — starts the bot and scheduler."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from trendposter.config import load_config
from trendposter.scheduler import Scheduler


def setup_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def run(args):
    config = load_config()
    setup_logging(config.log_level)
    logger = logging.getLogger("trendposter")

    # Validate X credentials
    from trendposter.poster import XPoster

    poster = XPoster(config.x)
    if not poster.validate_credentials():
        logger.error("X API credentials are invalid. Check your .env file.")
        sys.exit(1)

    logger.info(f"LLM provider: {config.llm.provider} ({config.llm.model})")

    # Create scheduler
    scheduler = Scheduler(config)

    # Start the cron scheduler
    cron = AsyncIOScheduler()
    if config.schedule.auto_post:
        cron.add_job(
            scheduler.run_cycle,
            "interval",
            minutes=config.schedule.check_interval_minutes,
            id="trend_check",
            max_instances=1,
        )

    bot = None

    if not args.scheduler_only:
        # Start bot
        platform = args.bot
        if not platform:
            # Auto-detect from config
            if config.bots:
                platform = config.bots[0].platform
            else:
                logger.error(
                    "No bot platform configured. "
                    "Set TELEGRAM_BOT_TOKEN or DISCORD_BOT_TOKEN, "
                    "or use --scheduler-only."
                )
                sys.exit(1)

        if platform == "telegram":
            from trendposter.bot.telegram_bot import TelegramBot

            bot = TelegramBot(config, scheduler)
        elif platform == "discord":
            from trendposter.bot.discord_bot import DiscordBot

            bot = DiscordBot(config, scheduler)
        else:
            logger.error(f"Unknown bot platform: {platform}")
            sys.exit(1)

        logger.info(f"Starting {platform} bot...")
        await bot.start()

    cron.start()
    if config.schedule.auto_post:
        logger.info(
            f"Scheduler running — checking trends every "
            f"{config.schedule.check_interval_minutes} minutes"
        )
    else:
        logger.info("Auto-posting disabled — use /top and /post to post manually")

    # Wait for shutdown signal
    stop_event = asyncio.Event()

    def handle_signal(*_):
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(sig, handle_signal)

    await stop_event.wait()

    logger.info("Shutting down...")
    cron.shutdown()
    if bot:
        await bot.stop()


def main():
    parser = argparse.ArgumentParser(
        description="TrendPoster — AI-powered tweet scheduler"
    )
    parser.add_argument(
        "--bot",
        choices=["telegram", "discord"],
        help="Bot platform to use (auto-detected if not specified)",
    )
    parser.add_argument(
        "--scheduler-only",
        action="store_true",
        help="Run only the scheduler, no bot interface",
    )
    parser.add_argument(
        "--env",
        help="Path to .env file (default: .env in current directory)",
    )
    args = parser.parse_args()

    if args.env:
        import os

        os.environ["DOTENV_PATH"] = args.env

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
