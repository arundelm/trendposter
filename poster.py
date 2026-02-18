"""X/Twitter poster — handles posting tweets via the X API."""

from __future__ import annotations

import logging

import tweepy

from trendposter.config import XConfig

logger = logging.getLogger(__name__)


class XPoster:
    """Posts tweets to X using the free-tier API."""

    def __init__(self, config: XConfig):
        self.client = tweepy.Client(
            consumer_key=config.api_key,
            consumer_secret=config.api_secret,
            access_token=config.access_token,
            access_token_secret=config.access_secret,
        )

    def post(self, text: str) -> dict:
        """Post a tweet. Returns the tweet data on success."""
        if len(text) > 280:
            raise ValueError(f"Tweet too long ({len(text)} chars, max 280)")

        try:
            response = self.client.create_tweet(text=text)
            tweet_id = response.data["id"]
            logger.info(f"Posted tweet {tweet_id}: {text[:50]}...")
            return {
                "id": tweet_id,
                "text": text,
                "url": f"https://x.com/i/status/{tweet_id}",
            }
        except tweepy.TweepyException as e:
            logger.error(f"Failed to post tweet: {e}")
            raise

    def validate_credentials(self) -> bool:
        """Check if credentials are valid."""
        try:
            me = self.client.get_me()
            if me.data:
                logger.info(f"Authenticated as @{me.data.username}")
                return True
            return False
        except tweepy.TweepyException as e:
            logger.error(f"Credential validation failed: {e}")
            return False
