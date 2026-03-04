"""Configuration loaded from environment variables."""

import logging
import os
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    shelfmark_url: str
    allowed_user_ids: list[int] = field(default_factory=list)
    log_level: str = "INFO"
    search_page_size: int = 10


def load_config() -> Config:
    """Load and validate configuration from environment variables."""
    missing: list[str] = []

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")

    url = os.environ.get("SHELFMARK_URL", "")
    if not url:
        missing.append("SHELFMARK_URL")

    if missing:
        print(
            f"ERROR: Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Parse optional allowed user IDs
    allowed_raw = os.environ.get("ALLOWED_USER_IDS", "")
    allowed_ids: list[int] = []
    if allowed_raw.strip():
        for uid in allowed_raw.split(","):
            uid = uid.strip()
            if uid:
                try:
                    allowed_ids.append(int(uid))
                except ValueError:
                    print(
                        f"WARNING: Ignoring invalid user ID in ALLOWED_USER_IDS: {uid!r}",
                        file=sys.stderr,
                    )

    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Normalise URL – strip trailing slash
    url = url.rstrip("/")

    return Config(
        telegram_bot_token=token,
        shelfmark_url=url,
        allowed_user_ids=allowed_ids,
        log_level=log_level,
    )


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger."""
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=getattr(logging, level, logging.INFO),
    )
