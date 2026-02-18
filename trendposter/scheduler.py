"""Scheduler — the core loop that checks trends and posts tweets."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from trendposter.config import Config
from trendposter.llm import TweetAnalysis, create_provider
from trendposter.poster import XPoster
from trendposter.queue import TweetQueue
from trendposter.scraper import TrendScraper

logger = logging.getLogger(__name__)


class Scheduler:
    """Orchestrates trend checking and tweet posting."""

    def __init__(self, config: Config):
        self.config = config
        self.queue = TweetQueue(config.database_path)
        self.scraper = TrendScraper()
        self.llm = create_provider(config.llm)
        self.poster = XPoster(config.x)

        # Callback for notifying bots
        self._notify_callback = None

    def set_notify_callback(self, callback):
        """Set a callback function for sending notifications to the user."""
        self._notify_callback = callback

    async def _notify(self, message: str):
        """Send a notification to the user via bot."""
        if self._notify_callback:
            try:
                await self._notify_callback(message)
            except Exception as e:
                logger.error(f"Notification failed: {e}")

    def _is_posting_hour(self) -> bool:
        """Check if current time is within allowed posting hours."""
        now = datetime.now(self.config.schedule.timezone)
        return (
            self.config.schedule.posting_hours_start
            <= now.hour
            < self.config.schedule.posting_hours_end
        )

    async def run_cycle(self, dry_run: bool = False) -> TweetAnalysis | None:
        """Run one analysis-and-post cycle.

        Returns the analysis if a tweet was posted (or would be in dry_run).
        """
        # 1. Check posting hours
        if not dry_run and not self._is_posting_hour():
            logger.info("Outside posting hours, skipping.")
            return None

        # 2. Get queued tweets
        queued = self.queue.list_queued()
        if not queued:
            logger.info("Queue is empty, nothing to analyze.")
            return None

        tweets_for_llm = [{"id": t.id, "text": t.text} for t in queued]

        # 3. Scrape trends
        trends = await self.scraper.get_trends()
        if not trends:
            logger.warning("No trends found, skipping cycle.")
            await self._notify("⚠️ Couldn't fetch trending topics. Will retry next cycle.")
            return None

        trends_text = self.scraper.get_trends_text(trends)
        logger.info(f"Fetched {len(trends)} trends")

        # 4. LLM analysis
        analysis = await self.llm.analyze_tweets(trends_text, tweets_for_llm)

        if analysis is None or not analysis.should_post:
            logger.info("No tweet matched current trends well enough.")
            return None

        # 5. Check minimum score
        if analysis.relevance_score < self.config.schedule.min_relevance_score:
            logger.info(
                f"Best match scored {analysis.relevance_score} "
                f"(min: {self.config.schedule.min_relevance_score}), skipping."
            )
            return analysis

        # 6. Post (or dry run)
        if dry_run:
            logger.info(f"[DRY RUN] Would post tweet #{analysis.tweet_id}: {analysis.tweet_text}")
            await self._notify(
                f"🔍 **Dry Run Analysis**\n\n"
                f"Would post: \"{analysis.tweet_text}\"\n"
                f"Matching trend: {analysis.matched_trend}\n"
                f"Score: {analysis.relevance_score}/100\n"
                f"Reason: {analysis.reasoning}"
            )
            return analysis

        try:
            # Find the queued tweet to get media info
            tweet_obj = next((t for t in queued if t.id == analysis.tweet_id), None)
            media_path = tweet_obj.media_path if tweet_obj else None
            result = self.poster.post(analysis.tweet_text, media_path=media_path)

            # Log it
            trends_json = json.dumps([{"name": t.name} for t in trends])
            self.queue.mark_posted(
                tweet_id=analysis.tweet_id,
                trend=analysis.matched_trend,
                score=analysis.relevance_score,
                reasoning=analysis.reasoning,
                trends_json=trends_json,
            )

            await self._notify(
                f"✅ **Posted!**\n\n"
                f"\"{analysis.tweet_text}\"\n\n"
                f"🔗 {result['url']}\n"
                f"📈 Matched trend: {analysis.matched_trend}\n"
                f"💯 Score: {analysis.relevance_score}/100\n"
                f"💬 {analysis.reasoning}\n\n"
                f"📋 {self.queue.queue_size()} tweets remaining in queue"
            )

            logger.info(
                f"Posted tweet #{analysis.tweet_id} "
                f"(trend: {analysis.matched_trend}, score: {analysis.relevance_score})"
            )
            return analysis

        except Exception as e:
            logger.error(f"Failed to post: {e}")
            await self._notify(f"❌ Failed to post tweet: {e}")
            return None

    async def rank_cycle(self, limit: int = 5) -> list[TweetAnalysis]:
        """Rank all queued tweets against current trends.

        Returns top `limit` results sorted by relevance score.
        """
        queued = self.queue.list_queued()
        if not queued:
            return []

        tweets_for_llm = [{"id": t.id, "text": t.text} for t in queued]

        trends = await self.scraper.get_trends()
        if not trends:
            return []

        trends_text = self.scraper.get_trends_text(trends)
        rankings = await self.llm.rank_tweets(trends_text, tweets_for_llm)
        return rankings[:limit]

    async def post_tweet_by_id(self, tweet_id: int) -> dict | None:
        """Post a specific tweet by its queue ID without LLM analysis."""
        queued = self.queue.list_queued()
        tweet = next((t for t in queued if t.id == tweet_id), None)
        if not tweet:
            return None

        try:
            result = self.poster.post(tweet.text, media_path=tweet.media_path)
            self.queue.mark_posted(
                tweet_id=tweet.id,
                trend="manual",
                score=0,
                reasoning="Manually posted by user",
                trends_json="[]",
            )
            return result
        except Exception as e:
            logger.error(f"Failed to post tweet #{tweet_id}: {e}")
            raise
