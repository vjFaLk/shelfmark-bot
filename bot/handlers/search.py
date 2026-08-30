"""Search handler – /search command and plain-text search (Direct mode)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.constants import ParseMode

from bot.handlers.releases import _filter_english, queue_download
from bot.shelfmark_client import ShelfmarkAPIError
from bot.utils import build_release_list_keyboard, escape, restricted

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
    await _do_search(update, context, " ".join(context.args))


@restricted
async def fast_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /fast <query> – download the top search result without asking."""
    if not context.args:
        await update.effective_message.reply_text(  # type: ignore[union-attr]
            "Usage: /fast <query>\n\nDownloads the most relevant result immediately."
        )
        return
    await _do_fast(update, context, " ".join(context.args))


async def _do_fast(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query: str
) -> None:
    """Search by relevance and queue the top hit."""
    msg = await update.effective_message.reply_text("⚡ Searching…")  # type: ignore[union-attr]

    import bot.state
    try:
        releases = _filter_english(
            await bot.state.shelfmark.search_books(query, sort="relevance")
        )
    except ShelfmarkAPIError as exc:
        await msg.edit_text(f"❌ Search failed: {escape(str(exc))}", parse_mode=ParseMode.HTML)
        return
    if not releases:
        await msg.edit_text("📭 No books found. Try a different query.")
        return

    # Shelfmark returns relevance order, stable-sorted by preferred format → [0] is best
    text, keyboard = await queue_download(
        releases[0], update.effective_chat.id, context  # type: ignore[union-attr]
    )
    await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@restricted
async def plain_text_search(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Treat any plain text message as a /fast query."""
    if not update.effective_message or not update.effective_message.text:
        return
    query = update.effective_message.text.strip()
    if query:
        await _do_fast(update, context, query)


async def _do_search(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query: str
) -> None:
    """Search the direct-download source and list releases."""
    import bot.state
    shelfmark = bot.state.shelfmark

    context.user_data["last_query"] = query  # type: ignore[index]
    msg = await update.effective_message.reply_text("🔍 Searching…")  # type: ignore[union-attr]

    try:
        releases = await shelfmark.search_books(query)
    except ShelfmarkAPIError as exc:
        await msg.edit_text(f"❌ Search failed: {escape(str(exc))}", parse_mode=ParseMode.HTML)
        return

    releases = _filter_english(releases)
    if not releases:
        await msg.edit_text("📭 No books found. Try a different query.")
        return

    # Each direct result IS a release – cache for dl:/confirm_dl: callbacks
    context.user_data["releases"] = {  # type: ignore[index]
        f"{r.get('source')}:{r.get('source_id')}": r for r in releases
    }

    await msg.edit_text(
        f"<b>Results for</b> <i>{escape(query)}</i> ({len(releases)})",
        parse_mode=ParseMode.HTML,
        reply_markup=build_release_list_keyboard(releases),
    )
