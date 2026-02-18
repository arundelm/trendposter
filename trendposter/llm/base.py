"""LLM provider abstraction — base class for all providers."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from trendposter.config import LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class TweetAnalysis:
    tweet_id: int
    tweet_text: str
    relevance_score: int  # 0-100
    matched_trend: str
    reasoning: str
    should_post: bool


ANALYSIS_PROMPT = """\
You are a social media strategist. Your job is to analyze a queue of draft tweets \
and determine which one (if any) is most relevant to the current trending topics on X/Twitter.

## Current Trending Topics
{trends}

## Queued Tweets
{tweets}

## Instructions
1. For each queued tweet, assess how well it connects to any current trend.
2. Pick the single best tweet to post RIGHT NOW based on trend relevance.
3. If no tweet is even slightly relevant to any trend, say so.

Respond with ONLY valid JSON (no markdown, no backticks):
{{
    "best_tweet_id": <id or null if none are relevant>,
    "relevance_score": <0-100>,
    "matched_trend": "<the trend it matches or null>",
    "reasoning": "<1-2 sentence explanation>",
    "should_post": <true/false>
}}
"""


RANKING_PROMPT = """\
You are a social media strategist. Your job is to score ALL queued tweets \
based on how relevant they are to the current trending topics on X/Twitter.

## Current Trending Topics
{trends}

## Queued Tweets
{tweets}

## Instructions
1. Score EVERY queued tweet from 0-100 based on relevance to current trends.
2. For each tweet, identify which trend it best matches (if any).
3. Provide a brief reason for each score.

Respond with ONLY valid JSON (no markdown, no backticks):
{{
    "rankings": [
        {{
            "id": <tweet id>,
            "relevance_score": <0-100>,
            "matched_trend": "<the trend it matches or null>",
            "reasoning": "<1 sentence explanation>"
        }}
    ]
}}

Sort the rankings array from highest to lowest relevance_score.
"""


def parse_ranking_response(
    response_text: str, tweets: list[dict]
) -> list[TweetAnalysis]:
    """Parse LLM JSON response into a list of ranked TweetAnalysis objects."""
    try:
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        rankings = data.get("rankings", [])

        tweet_map = {t["id"]: t["text"] for t in tweets}
        results = []
        for r in rankings:
            tid = r["id"]
            if tid not in tweet_map:
                continue
            results.append(
                TweetAnalysis(
                    tweet_id=tid,
                    tweet_text=tweet_map[tid],
                    relevance_score=int(r.get("relevance_score", 0)),
                    matched_trend=r.get("matched_trend") or "",
                    reasoning=r.get("reasoning", ""),
                    should_post=int(r.get("relevance_score", 0)) > 0,
                )
            )

        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse LLM ranking response: {e}\nRaw: {response_text[:500]}")
        return []


def format_tweets_for_prompt(tweets: list[dict]) -> str:
    """Format queued tweets for the LLM prompt."""
    lines = []
    for t in tweets:
        lines.append(f"- ID {t['id']}: \"{t['text']}\"")
    return "\n".join(lines)


def parse_analysis_response(response_text: str, tweets: list[dict]) -> TweetAnalysis | None:
    """Parse LLM JSON response into a TweetAnalysis."""
    try:
        # Strip any markdown wrapping
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)

        if not data.get("should_post") or data.get("best_tweet_id") is None:
            return None

        tweet_id = data["best_tweet_id"]
        tweet_text = next((t["text"] for t in tweets if t["id"] == tweet_id), "")

        return TweetAnalysis(
            tweet_id=tweet_id,
            tweet_text=tweet_text,
            relevance_score=int(data.get("relevance_score", 0)),
            matched_trend=data.get("matched_trend", ""),
            reasoning=data.get("reasoning", ""),
            should_post=bool(data.get("should_post", False)),
        )
    except (json.JSONDecodeError, KeyError, StopIteration) as e:
        logger.error(f"Failed to parse LLM response: {e}\nRaw: {response_text[:500]}")
        return None


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def complete(self, prompt: str) -> str:
        """Send a prompt and get a text response."""
        ...

    async def analyze_tweets(
        self, trends_text: str, tweets: list[dict]
    ) -> TweetAnalysis | None:
        """Analyze queued tweets against current trends."""
        if not tweets:
            return None

        prompt = ANALYSIS_PROMPT.format(
            trends=trends_text,
            tweets=format_tweets_for_prompt(tweets),
        )

        try:
            response = await self.complete(prompt)
            return parse_analysis_response(response, tweets)
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return None

    async def rank_tweets(
        self, trends_text: str, tweets: list[dict]
    ) -> list[TweetAnalysis]:
        """Rank all queued tweets against current trends."""
        if not tweets:
            return []

        prompt = RANKING_PROMPT.format(
            trends=trends_text,
            tweets=format_tweets_for_prompt(tweets),
        )

        try:
            response = await self.complete(prompt)
            return parse_ranking_response(response, tweets)
        except Exception as e:
            logger.error(f"LLM ranking failed: {e}")
            return []
