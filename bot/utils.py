"""Shared utilities – text formatting, keyboard builders, access control."""

from __future__ import annotations

import functools
import html
import logging
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Access control
# ------------------------------------------------------------------

ALLOWED_IDS: list[int] = []  # populated at startup from config


def set_allowed_ids(ids: list[int]) -> None:
    global ALLOWED_IDS
    ALLOWED_IDS = ids


def restricted(func):
    """Decorator that limits handler to allowed Telegram user IDs.

    If ALLOWED_IDS is empty, access is unrestricted.
    """

    @functools.wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        if ALLOWED_IDS:
            user = update.effective_user
            if user is None or user.id not in ALLOWED_IDS:
                if update.callback_query:
                    await update.callback_query.answer(
                        "⛔ Access denied.", show_alert=True
                    )
                elif update.effective_message:
                    await update.effective_message.reply_text("⛔ Access denied.")
                return
        return await func(update, context, *args, **kwargs)

    return wrapper


# ------------------------------------------------------------------
# Text helpers
# ------------------------------------------------------------------


def escape(text: str | None) -> str:
    """HTML-escape a string, returning empty string for None."""
    if not text:
        return ""
    return html.escape(str(text))


def truncate(text: str, max_len: int = 300) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def format_release(release: dict[str, Any]) -> str:
    """Short summary of a release for inline button label."""
    extra = release.get("extra") or {}
    fmt = (release.get("format") or "?").upper()
    size = release.get("size") or "?"
    title = release.get("title") or "Unknown"
    author = extra.get("author") or ""
    label = f"{title[:40]} – {author[:25]}" if author else title[:60]
    return f"{label} · {fmt} · {size}"


def format_release_detail(release: dict[str, Any]) -> str:
    """Multi-line detail for a release used in confirmation."""
    lines: list[str] = []
    extra = release.get("extra") or {}
    lines.append(f"📄 <b>{escape(release.get('title', 'Unknown'))}</b>")
    if extra.get("author"):
        lines.append(f"✍️ {escape(extra['author'])}")
    if extra.get("year"):
        lines.append(f"📅 {escape(extra['year'])}")
    if release.get("format"):
        lines.append(f"Format: {escape(release['format'].upper())}")
    if release.get("size"):
        lines.append(f"Size: {escape(release['size'])}")
    source = (release.get("source") or "").replace("_", " ").title()
    lines.append(f"Source: {source}")
    if release.get("indexer"):
        lines.append(f"Indexer: {escape(release['indexer'])}")
    if release.get("seeders") is not None:
        lines.append(f"Seeders: {release['seeders']}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Status formatting
# ------------------------------------------------------------------


def format_status(status: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Format download-queue status for display.

    Returns (formatted_text, list_of_completed_items).
    The actual API returns dicts keyed by book ID, not lists.
    """
    lines: list[str] = []

    def _items(key: str) -> list[dict[str, Any]]:
        """Extract items from a status category (dict-of-dicts → list)."""
        raw = status.get(key)
        if isinstance(raw, dict):
            return list(raw.values())
        if isinstance(raw, list):
            return raw
        return []

    downloading = _items("downloading")
    resolving = _items("resolving")
    locating = _items("locating")
    queued = _items("queued")
    completed = _items("complete") or _items("done")
    failed = _items("error")

    if downloading:
        lines.append("<b>⬇️ Downloading</b>")
        for item in downloading:
            title = escape(item.get("title", "Unknown"))
            progress = item.get("progress")
            pct = f" ({progress:.0f}%)" if progress is not None else ""
            msg = escape(item.get("status_message") or "")
            detail = f" — {msg}" if msg else ""
            lines.append(f"  • {title}{pct}{detail}")
        lines.append("")

    active = resolving + locating
    if active:
        lines.append("<b>🔄 Processing</b>")
        for item in active:
            title = escape(item.get("title", "Unknown"))
            msg = escape(item.get("status_message") or "")
            detail = f" — {msg}" if msg else ""
            lines.append(f"  • {title}{detail}")
        lines.append("")

    if queued:
        lines.append("<b>🕐 Queued</b>")
        for item in queued:
            title = escape(item.get("title", "Unknown"))
            lines.append(f"  • {title}")
        lines.append("")

    if completed:
        lines.append(f"<b>✅ Completed</b> ({len(completed)})")
        for item in completed[:10]:
            title = escape(item.get("title", "Unknown"))
            fmt = item.get("format", "")
            fmt_str = f" [{fmt.upper()}]" if fmt else ""
            lines.append(f"  • {title}{fmt_str}")
        if len(completed) > 10:
            lines.append(f"  … and {len(completed) - 10} more")
        lines.append("")

    if failed:
        lines.append(f"<b>❌ Failed</b> ({len(failed)})")
        for item in failed[:5]:
            title = escape(item.get("title", "Unknown"))
            msg = escape(item.get("status_message") or "")
            detail = f" — {msg}" if msg else ""
            lines.append(f"  • {title}{detail}")
        if len(failed) > 5:
            lines.append(f"  … and {len(failed) - 5} more")
        lines.append("")

    if not lines:
        lines.append("📭 No active downloads or queue items.")

    return "\n".join(lines), completed


# ------------------------------------------------------------------
# Keyboard builders
# ------------------------------------------------------------------


def build_release_list_keyboard(
    releases: list[dict[str, Any]],
) -> InlineKeyboardMarkup:
    """Inline keyboard for search results – one button per release."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=f"{i + 1}. {format_release(r)}",
                    callback_data=f"dl:{r.get('source', '')}:{r.get('source_id', '')}",
                )
            ]
            for i, r in enumerate(releases[:20])  # cap to avoid Telegram limits
        ]
    )
