"""Releases handler – list releases, filter by source, trigger download."""

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


def _pick_best_release(releases: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the best release: prefer direct_download epub, then prowlarr epub, then any."""

    def is_epub(r: dict) -> bool:
        fmt = (r.get("format") or "").lower()
        return fmt in ("epub", ".epub")

    # 1. Direct download epub
    for r in releases:
        if r.get("source") == "direct_download" and is_epub(r):
            return r
    # 2. Prowlarr epub
    for r in releases:
        if r.get("source") == "prowlarr" and is_epub(r):
            return r
    # 3. Direct download any format
    for r in releases:
        if r.get("source") == "direct_download":
            return r
    # 4. Prowlarr any format
    for r in releases:
        if r.get("source") == "prowlarr":
            return r
    # 5. Whatever is first
    return releases[0]


@restricted
async def auto_download_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle auto_dl:<provider>:<book_id> – auto-pick best release and confirm."""
    query_cb = update.callback_query
    if not query_cb:
        return
    await query_cb.answer()

    data = query_cb.data or ""
    parts = data.split(":", 2)
    if len(parts) < 3:
        return
    _, provider, book_id = parts

    import bot.state
    shelfmark = bot.state.shelfmark

    # Get book metadata for search hints
    cache_key = f"{provider}:{book_id}"
    book: dict[str, Any] = (context.user_data or {}).get("books", {}).get(
        cache_key, {}
    )
    title = book.get("title") or book.get("search_title")
    authors = book.get("authors") or []
    author = authors[0] if authors else None

    await query_cb.edit_message_text("🔍 Finding best release…")

    try:
        result = await shelfmark.get_releases(
            provider, book_id, title=title, author=author
        )
    except ShelfmarkAPIError as exc:
        await query_cb.edit_message_text(
            f"❌ Failed to find releases: {escape(str(exc))}",
            parse_mode=ParseMode.HTML,
        )
        return

    releases: list[dict] = result.get("releases") or []
    releases = _filter_english(releases)

    if not releases:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "◂ Back to book",
                        callback_data=f"book:{provider}:{book_id}",
                    )
                ]
            ]
        )
        await query_cb.edit_message_text(
            "📭 No releases found for this book.",
            reply_markup=keyboard,
        )
        return

    # Cache all releases
    context.user_data["releases"] = {  # type: ignore[index]
        f"{r.get('source')}:{r.get('source_id')}": r for r in releases
    }
    context.user_data["releases_book"] = cache_key  # type: ignore[index]

    picked = _pick_best_release(releases)
    source = picked.get("source", "")
    source_id = picked.get("source_id", "")

    text = "⬇️ <b>Confirm download?</b>\n\n" + format_release_detail(picked)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Confirm Download",
                    callback_data=f"confirm_dl:{source}:{source_id}",
                ),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_dl"),
            ],
            [
                InlineKeyboardButton(
                    "📋 Browse all releases",
                    callback_data=f"releases:{provider}:{book_id}",
                )
            ],
        ]
    )

    await query_cb.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


@restricted
async def releases_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle releases:<provider>:<book_id> – fetch and show releases."""
    query_cb = update.callback_query
    if not query_cb:
        return
    await query_cb.answer()

    data = query_cb.data or ""
    parts = data.split(":", 2)
    if len(parts) < 3:
        return
    _, provider, book_id = parts

    import bot.state
    shelfmark = bot.state.shelfmark

    # Get book metadata for search hints
    cache_key = f"{provider}:{book_id}"
    book: dict[str, Any] = (context.user_data or {}).get("books", {}).get(
        cache_key, {}
    )
    title = book.get("title") or book.get("search_title")
    authors = book.get("authors") or []
    author = authors[0] if authors else None

    # Show loading state
    try:
        await query_cb.edit_message_text("🔍 Searching for releases…")
    except Exception:
        await query_cb.edit_message_caption("🔍 Searching for releases…")

    try:
        result = await shelfmark.get_releases(
            provider, book_id, title=title, author=author
        )
    except ShelfmarkAPIError as exc:
        try:
            await query_cb.edit_message_text(
                f"❌ Failed to find releases: {escape(str(exc))}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await query_cb.edit_message_caption(
                f"❌ Failed to find releases: {escape(str(exc))}",
                parse_mode=ParseMode.HTML,
            )
        return

    releases: list[dict] = result.get("releases") or []
    releases = _filter_english(releases)

    if not releases:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "◂ Back to book",
                        callback_data=f"book:{provider}:{book_id}",
                    )
                ]
            ]
        )
        try:
            await query_cb.edit_message_text(
                "📭 No releases found for this book.",
                reply_markup=keyboard,
            )
        except Exception:
            await query_cb.edit_message_caption(
                "📭 No releases found for this book.",
                reply_markup=keyboard,
            )
        return

    # Cache releases
    context.user_data["releases"] = {  # type: ignore[index]
        f"{r.get('source')}:{r.get('source_id')}": r for r in releases
    }
    context.user_data["releases_book"] = cache_key  # type: ignore[index]

    text = f"📦 <b>{len(releases)} release(s) found</b>\nPick one to download:"
    keyboard = build_release_list_keyboard(releases, provider, book_id)

    try:
        await query_cb.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    except Exception:
        # If previous message was a photo, delete and send new text message
        try:
            await query_cb.message.delete()  # type: ignore[union-attr]
        except Exception:
            pass
        await update.effective_chat.send_message(  # type: ignore[union-attr]
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


@restricted
async def release_filter_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle rf:<source>:<provider>:<book_id> – filter releases by source."""
    query_cb = update.callback_query
    if not query_cb:
        return
    await query_cb.answer()

    data = query_cb.data or ""
    parts = data.split(":", 3)
    if len(parts) < 4:
        return
    _, source_filter, provider, book_id = parts

    releases_dict: dict = (context.user_data or {}).get("releases", {})
    releases = list(releases_dict.values())

    if not releases:
        await query_cb.edit_message_text("Releases expired. Please search again.")
        return

    actual_filter = None if source_filter == "all" else source_filter
    keyboard = build_release_list_keyboard(
        releases, provider, book_id, source_filter=actual_filter
    )

    count = len(releases)
    if actual_filter:
        count = len([r for r in releases if r.get("source") == actual_filter])

    text = f"📦 <b>{count} release(s)</b> "
    if actual_filter:
        text += f"from <i>{escape(actual_filter.replace('_', ' ').title())}</i>\n"
    else:
        text += "(all sources)\n"
    text += "Pick one to download:"

    await query_cb.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


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

    # Get book info for back button
    book_key = (context.user_data or {}).get("releases_book", "")
    book_parts = book_key.split(":", 1) if book_key else []

    back_buttons: list[InlineKeyboardButton] = []
    if len(book_parts) == 2:
        back_buttons.append(
            InlineKeyboardButton(
                "◂ Back to releases",
                callback_data=f"releases:{book_parts[0]}:{book_parts[1]}",
            )
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Confirm Download",
                    callback_data=f"confirm_dl:{source}:{source_id}",
                ),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_dl"),
            ],
            back_buttons,
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

    import bot.state
    shelfmark = bot.state.shelfmark

    await query_cb.edit_message_text("⏳ Queuing download…")

    try:
        result = await shelfmark.download_release(
            source=release.get("source", source),
            source_id=release.get("source_id", source_id),
            title=release.get("title", "Unknown"),
            fmt=release.get("format"),
            size=release.get("size"),
            extra=release.get("extra"),
            download_url=release.get("download_url"),
            content_type=release.get("content_type"),
        )
    except ShelfmarkAPIError as exc:
        await query_cb.edit_message_text(
            f"❌ Download failed: {escape(str(exc))}",
            parse_mode=ParseMode.HTML,
        )
        return

    import asyncio
    from bot.handlers.status import poll_and_send_file

    status = result.get("status", "unknown")
    title_text = release.get("title", "Unknown")
    title_escaped = escape(title_text)

    # Try to get the book_id (MD5) for polling — it's the source_id for direct downloads
    book_id = release.get("source_id", source_id)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📊 Check Status", callback_data="refresh_status"
                )
            ]
        ]
    )

    await query_cb.edit_message_text(
        f"✅ <b>Download queued!</b>\n\n"
        f"Title: {title_escaped}\n"
        f"Status: {status}\n\n"
        f"I'll send you the file when it's ready.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )

    # Start background polling to auto-send the file once complete
    chat_id = update.effective_chat.id  # type: ignore[union-attr]
    asyncio.create_task(
        poll_and_send_file(chat_id, book_id, title_text, context)
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

    book_key = (context.user_data or {}).get("releases_book", "")
    if book_key:
        parts = book_key.split(":", 1)
        if len(parts) == 2:
            # Re-render releases
            releases_dict: dict = (context.user_data or {}).get("releases", {})
            releases = list(releases_dict.values())
            if releases:
                keyboard = build_release_list_keyboard(
                    releases, parts[0], parts[1]
                )
                await query_cb.edit_message_text(
                    f"📦 <b>{len(releases)} release(s) found</b>\nPick one to download:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                return

    await query_cb.edit_message_text("Download cancelled.")
