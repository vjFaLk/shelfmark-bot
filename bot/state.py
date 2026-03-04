"""Global application state – shared across handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.shelfmark_client import ShelfmarkClient

# Populated by main() before polling starts.
shelfmark: ShelfmarkClient | None = None
