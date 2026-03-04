"""Status handler – /status command, refresh, and file download."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode

from bot.shelfmark_client import ShelfmarkAPIError
from bot.utils import escape, format_status, restricted

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Telegram file-send limit: 50 MB
_TG_FILE_LIMIT = 50 * 1024 * 1024


def _build_status_keyboard(completed_items: list[dict]) -> InlineKeyboardMarkup:
    """Build keyboard with download buttons for completed items + refresh."""
    buttons: list[list[InlineKeyboardButton]] = []

    for item in completed_items[:10]:
        book_id = item.get("id", "")
        title = item.get("title", "Unknown")
        fmt = (item.get("format") or "").upper()
        label = f"📥 {title[:35]}"
        if fmt:
            label += f" [{fmt}]"
        if len(label) > 55:
            label = label[:52] + "…"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"get_file:{book_id}")]
        )

    buttons.append(
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")]
    )
    return InlineKeyboardMarkup(buttons)


@restricted
async def status_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /status command."""
    import bot.state
    shelfmark = bot.state.shelfmark

    msg = await update.effective_message.reply_text("📊 Fetching status…")  # type: ignore[union-attr]

    try:
        status = await shelfmark.get_status()
    except ShelfmarkAPIError as exc:
        await msg.edit_text(
            f"❌ Failed to fetch status: {escape(str(exc))}",
            parse_mode=ParseMode.HTML,
        )
        return

    text, completed = format_status(status)
    keyboard = _build_status_keyboard(completed)

    await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@restricted
async def refresh_status_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle refresh_status callback."""
    query_cb = update.callback_query
    if not query_cb:
        return
    await query_cb.answer()

    import bot.state
    shelfmark = bot.state.shelfmark

    try:
        status = await shelfmark.get_status()
    except ShelfmarkAPIError as exc:
        await query_cb.edit_message_text(
            f"❌ Failed to fetch status: {escape(str(exc))}",
            parse_mode=ParseMode.HTML,
        )
        return

    text, completed = format_status(status)
    keyboard = _build_status_keyboard(completed)

    try:
        await query_cb.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    except Exception:
        # Message unchanged – Telegram raises error if text is identical
        pass


@restricted
async def send_file_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle get_file:<book_id> – download file from Shelfmark and send to user."""
    query_cb = update.callback_query
    if not query_cb:
        return
    await query_cb.answer("Fetching file…")

    data = query_cb.data or ""
    parts = data.split(":", 1)
    if len(parts) < 2:
        return
    book_id = parts[1]

    import bot.state
    shelfmark = bot.state.shelfmark

    try:
        file_bytes, filename = await shelfmark.download_file(book_id)
    except ShelfmarkAPIError as exc:
        await query_cb.edit_message_text(
            f"❌ Failed to download file: {escape(str(exc))}",
            parse_mode=ParseMode.HTML,
        )
        return

    if len(file_bytes) > _TG_FILE_LIMIT:
        await query_cb.edit_message_text(
            f"❌ File too large for Telegram ({len(file_bytes) / 1024 / 1024:.1f} MB, limit 50 MB)."
        )
        return

    # Send as document
    chat = update.effective_chat
    if not chat:
        return

    await chat.send_document(
        document=io.BytesIO(file_bytes),
        filename=filename,
        caption=f"📚 {escape(filename)}",
        parse_mode=ParseMode.HTML,
        read_timeout=120,
        write_timeout=120,
    )


async def poll_and_send_file(
    chat_id: int,
    book_id: str,
    title: str,
    context: ContextTypes.DEFAULT_TYPE,
    max_wait: int = 600,
    interval: int = 10,
) -> None:
    """Poll Shelfmark status until the book is complete, then send the file.

    Called as a background task after a download is queued.
    """
    import bot.state
    shelfmark = bot.state.shelfmark
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(interval)
        elapsed += interval

        try:
            status = await shelfmark.get_status()
        except Exception:
            logger.debug("Poll status failed, retrying…", exc_info=True)
            continue

        # Check if our book_id is in completed categories
        for key in ("complete", "done"):
            cat = status.get(key)
            if isinstance(cat, dict) and book_id in cat:
                # Book is done — send the file
                try:
                    file_bytes, filename = await shelfmark.download_file(book_id)
                    if len(file_bytes) <= _TG_FILE_LIMIT:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=io.BytesIO(file_bytes),
                            filename=filename,
                            caption=f"📚 {escape(filename)}",
                            parse_mode=ParseMode.HTML,
                            read_timeout=120,
                            write_timeout=120,
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"✅ <b>{escape(title)}</b> finished downloading but the file is too large for Telegram ({len(file_bytes) / 1024 / 1024:.1f} MB).",
                            parse_mode=ParseMode.HTML,
                        )
                except Exception:
                    logger.error("Failed to send completed file", exc_info=True)
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"✅ <b>{escape(title)}</b> finished downloading. Use /status to get the file.",
                        parse_mode=ParseMode.HTML,
                    )
                return

        # Check if it errored
        error_cat = status.get("error")
        if isinstance(error_cat, dict) and book_id in error_cat:
            item = error_cat[book_id]
            msg = escape(item.get("status_message") or "Unknown error")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Download of <b>{escape(title)}</b> failed: {msg}",
                parse_mode=ParseMode.HTML,
            )
            return

    # Timed out
    logger.warning("Poll timed out for book %s after %ds", book_id, max_wait)
