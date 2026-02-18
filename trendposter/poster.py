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
        # v1.1 API needed for media uploads
        auth = tweepy.OAuth1UserHandler(
            config.api_key, config.api_secret,
            config.access_token, config.access_secret,
        )
        self.api = tweepy.API(auth)

    def _upload_media(self, media_path: str) -> int | None:
        """Upload media to X and return the media_id."""
        try:
            media = self.api.media_upload(filename=media_path)
            logger.info(f"Uploaded media: {media.media_id}")
            return media.media_id
        except tweepy.TweepyException as e:
            logger.error(f"Media upload failed: {e}")
            raise

    def post(self, text: str, media_path: str | None = None) -> dict:
        """Post a tweet, optionally with media. Returns the tweet data on success."""
        if text and len(text) > 280:
            raise ValueError(f"Tweet too long ({len(text)} chars, max 280)")

        try:
            media_ids = None
            if media_path:
                mid = self._upload_media(media_path)
                media_ids = [mid]

            kwargs = {}
            if text:
                kwargs["text"] = text
            if media_ids:
                kwargs["media_ids"] = media_ids

            response = self.client.create_tweet(**kwargs)
            tweet_id = response.data["id"]
            logger.info(f"Posted tweet {tweet_id}: {(text or '[media]')[:50]}...")
            return {
                "id": tweet_id,
                "text": text or "",
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
