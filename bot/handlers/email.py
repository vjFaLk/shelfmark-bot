"""Email handler – /email <query>: fast-download, then Grimmory Quick Send."""

from __future__ import annotations

import asyncio
import logging
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from telegram import Update
from telegram.constants import ParseMode

from bot.grimmory_client import GrimmoryAPIError
from bot.handlers.status import wait_for_download
from bot.utils import escape, restricted

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


@restricted
async def email_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /email <query> – download the top result and email it via Grimmory."""
    import bot.state
    from bot.handlers.search import _do_fast

    if not bot.state.grimmory:
        await update.effective_message.reply_text(  # type: ignore[union-attr]
            "Grimmory is not configured. Set GRIMMORY_URL, GRIMMORY_USERNAME and GRIMMORY_PASSWORD."
        )
        return
    if not context.args:
        await update.effective_message.reply_text(  # type: ignore[union-attr]
            "Usage: /email <query>\n\nDownloads the top result and emails it via Grimmory Quick Send."
        )
        return
    await _do_fast(update, context, " ".join(context.args), email=True)


def _book_title(book: dict[str, Any]) -> str:
    return (book.get("metadata") or {}).get("title") or book.get("title") or ""


def best_match(title: str, books: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the book whose Grimmory title is closest to the Shelfmark release title."""
    return max(
        books,
        key=lambda b: SequenceMatcher(None, title.lower(), _book_title(b).lower()).ratio(),
    )


async def poll_and_email(
    chat_id: int,
    book_id: str,
    title: str,
    watermark: int,
    context: ContextTypes.DEFAULT_TYPE,
    max_wait: int = 300,
    interval: int = 10,
) -> None:
    """Background task: wait for Shelfmark, wait for Grimmory ingest, Quick Send."""
    import bot.state
    grimmory = bot.state.grimmory

    if not await wait_for_download(chat_id, book_id, title, context):
        return

    new_books: list[dict[str, Any]] = []
    elapsed = 0
    while elapsed < max_wait and not new_books:
        await asyncio.sleep(interval)
        elapsed += interval
        try:
            new_books = await grimmory.books_after(watermark)
        except Exception:
            logger.debug("Grimmory poll failed, retrying…", exc_info=True)

    if not new_books:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ <b>{escape(title)}</b> finished downloading but never showed up in Grimmory.",
            parse_mode=ParseMode.HTML,
        )
        return

    book = best_match(title, new_books)
    try:
        await grimmory.quick_send(int(book["id"]))
    except GrimmoryAPIError as exc:
        text = f"❌ Quick Send failed for <b>{escape(_book_title(book))}</b>: {escape(str(exc))}"
    else:
        text = f"📧 Quick Send triggered for <b>{escape(_book_title(book))}</b>."
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
