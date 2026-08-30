"""Releases handler – confirm and trigger download."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode

from bot.shelfmark_client import ShelfmarkAPIError
from bot.utils import (
    build_release_list_keyboard,
    escape,
    format_release_detail,
    restricted,
)

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_ENGLISH_CODES = {"", "en", "eng", "english"}


def _is_english(release: dict[str, Any]) -> bool:
    """Return True if the release has no language tag or is tagged English."""
    lang = (release.get("language") or "").strip().lower()
    return lang in _ENGLISH_CODES


def _filter_english(releases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only English (or untagged) releases; fall back to all if none match."""
    filtered = [r for r in releases if _is_english(r)]
    return filtered if filtered else releases


@restricted
async def download_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle dl:<source>:<source_id> – show download confirmation."""
    query_cb = update.callback_query
    if not query_cb:
        return
    await query_cb.answer()

    data = query_cb.data or ""
    parts = data.split(":", 2)
    if len(parts) < 3:
        return
    _, source, source_id = parts

    release_key = f"{source}:{source_id}"
    release = (context.user_data or {}).get("releases", {}).get(release_key)

    if not release:
        await query_cb.edit_message_text(
            "Release data expired. Please search again."
        )
        return

    # Store for confirmation
    context.user_data["pending_download"] = release  # type: ignore[index]

    text = "⬇️ <b>Confirm download?</b>\n\n" + format_release_detail(release)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Confirm Download",
                    callback_data=f"confirm_dl:{source}:{source_id}",
                ),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_dl"),
            ],
        ]
    )

    await query_cb.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


@restricted
async def confirm_download_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle confirm_dl:<source>:<source_id> – actually queue the download."""
    query_cb = update.callback_query
    if not query_cb:
        return
    await query_cb.answer()

    data = query_cb.data or ""
    parts = data.split(":", 2)
    if len(parts) < 3:
        return
    _, source, source_id = parts

    release_key = f"{source}:{source_id}"
    release = (context.user_data or {}).get("releases", {}).get(release_key)

    if not release:
        await query_cb.edit_message_text(
            "Release data expired. Please search again."
        )
        return

    await query_cb.edit_message_text("⏳ Queuing download…")
    text, keyboard = await queue_download(release, update.effective_chat.id, context)  # type: ignore[union-attr]
    await query_cb.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def queue_download(
    release: dict[str, Any], chat_id: int, context: ContextTypes.DEFAULT_TYPE
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Queue a release and start background polling to auto-send the file.

    Returns (message_text, keyboard) for the caller to display.
    """
    import asyncio
    import bot.state
    from bot.handlers.status import poll_and_send_file

    title = release.get("title", "Unknown")
    try:
        result = await bot.state.shelfmark.download_release(
            source=release.get("source", ""),
            source_id=release.get("source_id", ""),
            title=title,
            fmt=release.get("format"),
            size=release.get("size"),
            extra=release.get("extra"),
            download_url=release.get("download_url"),
            content_type=release.get("content_type"),
        )
    except ShelfmarkAPIError as exc:
        return f"❌ Download failed: {escape(str(exc))}", None

    # source_id (MD5) is the book_id Shelfmark reports in /api/status
    asyncio.create_task(
        poll_and_send_file(chat_id, release.get("source_id", ""), title, context)
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📊 Check Status", callback_data="refresh_status")]]
    )
    return (
        f"✅ <b>Download queued!</b>\n\n"
        f"Title: {escape(title)}\n"
        f"Status: {result.get('status', 'unknown')}\n\n"
        f"I'll send you the file when it's ready.",
        keyboard,
    )


@restricted
async def cancel_download_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle cancel_dl callback – go back to releases."""
    query_cb = update.callback_query
    if not query_cb:
        return
    await query_cb.answer("Cancelled.")

    releases = list((context.user_data or {}).get("releases", {}).values())
    if releases:
        query = (context.user_data or {}).get("last_query", "")
        await query_cb.edit_message_text(
            f"<b>Results for</b> <i>{escape(query)}</i> ({len(releases)})",
            parse_mode=ParseMode.HTML,
            reply_markup=build_release_list_keyboard(releases),
        )
        return

    await query_cb.edit_message_text("Download cancelled.")
