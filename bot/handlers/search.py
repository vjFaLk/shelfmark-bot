"""Search handler – /search command and plain-text search."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.constants import ParseMode

from bot.shelfmark_client import ShelfmarkAPIError
from bot.utils import (
    build_book_list_keyboard,
    escape,
    format_book_list_item,
    restricted,
)

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


@restricted
async def search_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /search (or /s) command."""
    if not context.args:
        await update.effective_message.reply_text(  # type: ignore[union-attr]
            "Usage: /search <query>\n\nExample: /search The Hitchhiker's Guide"
        )
        return
    query = " ".join(context.args)
    await _do_search(update, context, query, page=1)


@restricted
async def plain_text_search(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Treat any plain text message as a search query."""
    if not update.effective_message or not update.effective_message.text:
        return
    query = update.effective_message.text.strip()
    if not query:
        return
    await _do_search(update, context, query, page=1)


@restricted
async def page_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle pagination: callback data = page:<num>."""
    query_cb = update.callback_query
    if not query_cb:
        return
    await query_cb.answer()

    data = query_cb.data or ""
    try:
        page = int(data.split(":")[1])
    except (IndexError, ValueError):
        return

    # Retrieve the stored search query
    query = (context.user_data or {}).get("last_query", "")
    if not query:
        await query_cb.edit_message_text("Search expired. Please search again.")
        return

    await _do_search(update, context, query, page=page, edit=True)


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------


async def _do_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query: str,
    page: int = 1,
    edit: bool = False,
) -> None:
    """Execute a search and display results."""
    import bot.state
    shelfmark = bot.state.shelfmark

    # Store query for pagination
    context.user_data["last_query"] = query  # type: ignore[index]

    # Send/edit a placeholder
    if edit and update.callback_query:
        await update.callback_query.edit_message_text("🔍 Searching…")
        msg = update.callback_query.message
    else:
        msg = await update.effective_message.reply_text("🔍 Searching…")  # type: ignore[union-attr]

    try:
        result = await shelfmark.search_books(query, page=page)
    except ShelfmarkAPIError as exc:
        await msg.edit_text(f"❌ Search failed: {escape(str(exc))}", parse_mode=ParseMode.HTML)  # type: ignore[union-attr]
        return

    books: list = result.get("books") or []
    has_more: bool = result.get("has_more", False)

    # # Filter to English-language books only
    # books = [
    #     b for b in books
    #     if (b.get("language") or "").lower() in ("english", "en", "eng", "")
    # ]

    if not books:
        await msg.edit_text("📭 No books found. Try a different query.")  # type: ignore[union-attr]
        return

    # Store books in user_data for later reference
    context.user_data["books"] = {  # type: ignore[index]
        f"{b.get('provider')}:{b.get('provider_id')}": b for b in books
    }
    context.user_data["search_page"] = page  # type: ignore[index]

    # Build message
    text = f"<b>Results for</b> <i>{escape(query)}</i> (page {page})"

    keyboard = build_book_list_keyboard(books, page, has_more, query)

    await msg.edit_text(  # type: ignore[union-attr]
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
