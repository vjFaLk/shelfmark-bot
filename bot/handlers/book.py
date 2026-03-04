"""Book detail handler – show full info for a selected book."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode

from bot.shelfmark_client import ShelfmarkAPIError
from bot.utils import escape, format_book_detail, restricted

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


@restricted
async def book_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle book:<provider>:<book_id> callback."""
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

    # Try cache first, then fetch
    cache_key = f"{provider}:{book_id}"
    book = (context.user_data or {}).get("books", {}).get(cache_key)

    if not book:
        try:
            book = await shelfmark.get_book(provider, book_id)
        except ShelfmarkAPIError as exc:
            await query_cb.edit_message_text(
                f"❌ Failed to load book: {escape(str(exc))}",
                parse_mode=ParseMode.HTML,
            )
            return

    # Store book for later use in releases
    context.user_data.setdefault("books", {})[cache_key] = book  # type: ignore[union-attr]
    context.user_data["current_book"] = cache_key  # type: ignore[index]

    text = format_book_detail(book)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⬇️ Download",
                    callback_data=f"auto_dl:{provider}:{book_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "◂ Back to results",
                    callback_data=f"page:{(context.user_data or {}).get('search_page', 1)}",
                )
            ],
        ]
    )

    await query_cb.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
