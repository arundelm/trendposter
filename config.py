"""Configuration management — loads from .env and validates."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass
class XConfig:
    api_key: str
    api_secret: str
    access_token: str
    access_secret: str


@dataclass
class LLMConfig:
    provider: str  # anthropic | openai | gemini | ollama
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@dataclass
class BotConfig:
    platform: str  # telegram | discord
    token: str


@dataclass
class ScheduleConfig:
    check_interval_minutes: int = 60
    posting_hours_start: int = 8
    posting_hours_end: int = 22
    min_relevance_score: int = 40
    auto_post: bool = True
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("UTC"))


@dataclass
class Config:
    x: XConfig
    llm: LLMConfig
    bots: list[BotConfig]
    schedule: ScheduleConfig
    database_path: Path = Path("./data/trendposter.db")
    log_level: str = "INFO"
    max_queue_size: int = 50
    allowed_user_ids: set[int] = field(default_factory=set)


# Default model per provider
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5-20250929",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
    "ollama": "llama3.2",
}

# Priority order when auto-detecting
PROVIDER_PRIORITY = ["anthropic", "openai", "gemini", "ollama"]

# Env var name for each provider's API key
PROVIDER_KEY_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama": None,  # No key needed
}


def _detect_llm_provider() -> LLMConfig:
    """Auto-detect which LLM provider to use based on available keys."""
    forced = os.getenv("LLM_PROVIDER", "").lower().strip()
    if forced:
        if forced == "ollama":
            return LLMConfig(
                provider="ollama",
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                model=os.getenv("OLLAMA_MODEL", DEFAULT_MODELS["ollama"]),
            )
        key_var = PROVIDER_KEY_VARS.get(forced)
        key = os.getenv(key_var, "") if key_var else None
        if key_var and not key:
            raise ValueError(f"LLM_PROVIDER={forced} but {key_var} is not set")
        return LLMConfig(
            provider=forced,
            api_key=key,
            model=os.getenv("LLM_MODEL", DEFAULT_MODELS.get(forced)),
        )

    # Auto-detect by priority
    for provider in PROVIDER_PRIORITY:
        key_var = PROVIDER_KEY_VARS.get(provider)
        if key_var is None:
            # Ollama — check if base URL is set
            if os.getenv("OLLAMA_BASE_URL"):
                return LLMConfig(
                    provider="ollama",
                    base_url=os.getenv("OLLAMA_BASE_URL"),
                    model=os.getenv("OLLAMA_MODEL", DEFAULT_MODELS["ollama"]),
                )
            continue
        key = os.getenv(key_var, "").strip()
        if key:
            return LLMConfig(
                provider=provider,
                api_key=key,
                model=os.getenv("LLM_MODEL", DEFAULT_MODELS[provider]),
            )

    raise ValueError(
        "No LLM provider configured. Set at least one of: "
        "ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, or OLLAMA_BASE_URL"
    )


def _detect_bots() -> list[BotConfig]:
    """Detect configured bot platforms."""
    bots = []
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if tg_token:
        bots.append(BotConfig(platform="telegram", token=tg_token))
    dc_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if dc_token:
        bots.append(BotConfig(platform="discord", token=dc_token))
    return bots


def load_config(env_path: str | Path | None = None) -> Config:
    """Load and validate configuration from .env file."""
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()

    # X API — required
    x_key = os.getenv("X_API_KEY", "").strip()
    x_secret = os.getenv("X_API_SECRET", "").strip()
    x_access = os.getenv("X_ACCESS_TOKEN", "").strip()
    x_access_secret = os.getenv("X_ACCESS_SECRET", "").strip()

    if not all([x_key, x_secret, x_access, x_access_secret]):
        raise ValueError(
            "Missing X API credentials. Set X_API_KEY, X_API_SECRET, "
            "X_ACCESS_TOKEN, and X_ACCESS_SECRET in your .env file."
        )

    x_config = XConfig(
        api_key=x_key,
        api_secret=x_secret,
        access_token=x_access,
        access_secret=x_access_secret,
    )

    # LLM
    llm_config = _detect_llm_provider()

    # Bots
    bots = _detect_bots()

    # Schedule
    tz_str = os.getenv("TIMEZONE", "UTC").strip()
    try:
        tz = ZoneInfo(tz_str)
    except (KeyError, ValueError):
        raise ValueError(f"Invalid timezone: {tz_str}")

    schedule = ScheduleConfig(
        check_interval_minutes=int(os.getenv("CHECK_INTERVAL_MINUTES", "60")),
        posting_hours_start=int(os.getenv("POSTING_HOURS_START", "8")),
        posting_hours_end=int(os.getenv("POSTING_HOURS_END", "22")),
        min_relevance_score=int(os.getenv("MIN_RELEVANCE_SCORE", "40")),
        auto_post=os.getenv("AUTO_POST", "true").lower().strip() in ("true", "1", "yes"),
        timezone=tz,
    )

    db_path = Path(os.getenv("DATABASE_PATH", "./data/trendposter.db"))

    # Allowed user IDs (comma-separated)
    raw_ids = os.getenv("ALLOWED_USER_IDS", "").strip()
    allowed_ids = set()
    if raw_ids:
        for uid in raw_ids.split(","):
            uid = uid.strip()
            if uid.isdigit():
                allowed_ids.add(int(uid))

    return Config(
        x=x_config,
        llm=llm_config,
        bots=bots,
        schedule=schedule,
        database_path=db_path,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        max_queue_size=int(os.getenv("MAX_QUEUE_SIZE", "50")),
        allowed_user_ids=allowed_ids,
    )
