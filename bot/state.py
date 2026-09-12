"""Global application state – shared across handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.grimmory_client import GrimmoryClient
    from bot.shelfmark_client import ShelfmarkClient

# Populated by main() before polling starts.
shelfmark: ShelfmarkClient | None = None
grimmory: GrimmoryClient | None = None  # None when GRIMMORY_* env vars are unset
