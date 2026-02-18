"""Tweet queue — SQLite-backed storage for draft tweets."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class QueuedTweet:
    id: int
    text: str
    added_at: str
    posted_at: str | None = None
    relevance_score: float | None = None
    matched_trend: str | None = None
    status: str = "queued"  # queued | posted | expired | removed
    media_path: str | None = None
    media_type: str | None = None  # photo | video | None


class TweetQueue:
    """Manages the tweet queue in SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tweets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL DEFAULT '',
                    added_at TEXT NOT NULL,
                    posted_at TEXT,
                    relevance_score REAL,
                    matched_trend TEXT,
                    status TEXT NOT NULL DEFAULT 'queued',
                    media_path TEXT,
                    media_type TEXT
                )
            """)
            # Migrate existing DBs that lack media columns
            try:
                conn.execute("SELECT media_path FROM tweets LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE tweets ADD COLUMN media_path TEXT")
                conn.execute("ALTER TABLE tweets ADD COLUMN media_type TEXT")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS post_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tweet_id INTEGER NOT NULL,
                    tweet_text TEXT NOT NULL,
                    trends TEXT,
                    reasoning TEXT,
                    relevance_score REAL,
                    posted_at TEXT NOT NULL,
                    FOREIGN KEY (tweet_id) REFERENCES tweets(id)
                )
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def add(
        self, text: str, media_path: str | None = None, media_type: str | None = None
    ) -> QueuedTweet:
        """Add a tweet to the queue, optionally with media."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO tweets (text, added_at, status, media_path, media_type) "
                "VALUES (?, ?, 'queued', ?, ?)",
                (text, now, media_path, media_type),
            )
            return QueuedTweet(
                id=cursor.lastrowid, text=text, added_at=now,
                media_path=media_path, media_type=media_type,
            )

    def list_queued(self) -> list[QueuedTweet]:
        """Get all queued (unposted) tweets."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tweets WHERE status = 'queued' ORDER BY added_at ASC"
            ).fetchall()
            return [QueuedTweet(**dict(r)) for r in rows]

    def remove(self, tweet_id: int) -> bool:
        """Remove a tweet from the queue."""
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE tweets SET status = 'removed' WHERE id = ? AND status = 'queued'",
                (tweet_id,),
            )
            return cursor.rowcount > 0

    def mark_posted(
        self,
        tweet_id: int,
        trend: str,
        score: float,
        reasoning: str,
        trends_json: str,
    ):
        """Mark a tweet as posted and log details."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """UPDATE tweets
                   SET status = 'posted', posted_at = ?, matched_trend = ?, relevance_score = ?
                   WHERE id = ?""",
                (now, trend, score, tweet_id),
            )
            conn.execute(
                """INSERT INTO post_log
                   (tweet_id, tweet_text, trends, reasoning, relevance_score, posted_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    tweet_id,
                    self._get_text(conn, tweet_id),
                    trends_json,
                    reasoning,
                    score,
                    now,
                ),
            )

    def _get_text(self, conn: sqlite3.Connection, tweet_id: int) -> str:
        row = conn.execute("SELECT text FROM tweets WHERE id = ?", (tweet_id,)).fetchone()
        return row["text"] if row else ""

    def get_post_history(self, limit: int = 10) -> list[dict]:
        """Get recent post history."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM post_log ORDER BY posted_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def queue_size(self) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM tweets WHERE status = 'queued'"
            ).fetchone()
            return row["cnt"]
