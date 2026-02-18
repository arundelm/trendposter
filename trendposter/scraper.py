"""Trend scraper — fetches current X/Twitter trending topics without API read access."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class Trend:
    name: str
    category: str | None = None
    tweet_count: str | None = None


# Multiple sources for resilience
TREND_SOURCES = [
    {
        "name": "trends24",
        "url": "https://trends24.in/united-states/",
        "parser": "_parse_trends24",
    },
    {
        "name": "getdaytrends",
        "url": "https://getdaytrends.com/united-states/",
        "parser": "_parse_getdaytrends",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


class TrendScraper:
    """Scrapes trending topics from public trend aggregator sites."""

    def __init__(self, country: str = "united-states"):
        self.country = country

    async def get_trends(self) -> list[Trend]:
        """Fetch current trending topics. Tries multiple sources."""
        for source in TREND_SOURCES:
            try:
                trends = await self._fetch_source(source)
                if trends:
                    logger.info(
                        f"Got {len(trends)} trends from {source['name']}"
                    )
                    return trends[:30]  # Top 30 is plenty
            except Exception as e:
                logger.warning(f"Failed to fetch from {source['name']}: {e}")
                continue

        logger.error("All trend sources failed")
        return []

    async def _fetch_source(self, source: dict) -> list[Trend]:
        """Fetch and parse a single trend source."""
        async with httpx.AsyncClient(
            headers=HEADERS, follow_redirects=True, timeout=15
        ) as client:
            url = source["url"].replace("united-states", self.country)
            resp = await client.get(url)
            resp.raise_for_status()
            parser = getattr(self, source["parser"])
            return parser(resp.text)

    @staticmethod
    def _parse_trends24(html: str) -> list[Trend]:
        """Parse trends from trends24.in."""
        soup = BeautifulSoup(html, "lxml")
        trends = []
        seen = set()

        # trends24 uses ordered lists within trend cards
        for card in soup.select(".trend-card"):
            for li in card.select("ol li a"):
                name = li.get_text(strip=True)
                if name and name.lower() not in seen:
                    seen.add(name.lower())
                    trends.append(Trend(name=name))

        return trends

    @staticmethod
    def _parse_getdaytrends(html: str) -> list[Trend]:
        """Parse trends from getdaytrends.com."""
        soup = BeautifulSoup(html, "lxml")
        trends = []
        seen = set()

        for row in soup.select("table.table tbody tr"):
            cells = row.select("td")
            if cells:
                name_el = cells[0].select_one("a")
                if name_el:
                    name = name_el.get_text(strip=True)
                    if name and name.lower() not in seen:
                        seen.add(name.lower())
                        count = cells[1].get_text(strip=True) if len(cells) > 1 else None
                        trends.append(Trend(name=name, tweet_count=count))

        return trends

    def get_trends_text(self, trends: list[Trend]) -> str:
        """Format trends as a readable string for the LLM prompt."""
        if not trends:
            return "No trending topics found."
        lines = []
        for i, t in enumerate(trends, 1):
            line = f"{i}. {t.name}"
            if t.tweet_count:
                line += f" ({t.tweet_count} tweets)"
            if t.category:
                line += f" [{t.category}]"
            lines.append(line)
        return "\n".join(lines)
