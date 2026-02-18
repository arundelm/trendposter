"""Tests for the tweet queue."""

import tempfile
from pathlib import Path

from trendposter.queue import TweetQueue


def test_add_and_list():
    with tempfile.TemporaryDirectory() as tmp:
        q = TweetQueue(Path(tmp) / "test.db")
        tweet = q.add("Hello world!")
        assert tweet.id == 1
        assert tweet.text == "Hello world!"

        queued = q.list_queued()
        assert len(queued) == 1
        assert queued[0].text == "Hello world!"


def test_remove():
    with tempfile.TemporaryDirectory() as tmp:
        q = TweetQueue(Path(tmp) / "test.db")
        tweet = q.add("To be removed")
        assert q.remove(tweet.id) is True
        assert q.list_queued() == []
        assert q.remove(999) is False


def test_queue_size():
    with tempfile.TemporaryDirectory() as tmp:
        q = TweetQueue(Path(tmp) / "test.db")
        assert q.queue_size() == 0
        q.add("One")
        q.add("Two")
        assert q.queue_size() == 2


def test_mark_posted():
    with tempfile.TemporaryDirectory() as tmp:
        q = TweetQueue(Path(tmp) / "test.db")
        tweet = q.add("Posted tweet")
        q.mark_posted(
            tweet_id=tweet.id,
            trend="AI",
            score=85.0,
            reasoning="Matched AI trend",
            trends_json='[{"name": "AI"}]',
        )
        # Should no longer be in queued list
        assert q.list_queued() == []
        # Should appear in history
        history = q.get_post_history()
        assert len(history) == 1
        assert history[0]["relevance_score"] == 85.0
