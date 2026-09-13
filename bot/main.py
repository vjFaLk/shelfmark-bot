"""Shelfmark Telegram Bot – entry point."""

from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.config import Config, load_config, setup_logging
from bot.grimmory_client import GrimmoryClient
from bot.handlers.email import email_command
from bot.handlers.releases import (
    cancel_download_callback,
    confirm_download_callback,
    download_callback,
)
from bot.handlers.search import fast_command, plain_text_search, search_command, send_command
from bot.handlers.status import refresh_status_callback, send_file_callback, status_command
from bot.shelfmark_client import ShelfmarkClient
from bot.utils import set_allowed_ids

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Called after the Application is initialised – set bot commands."""
    await application.bot.set_my_commands(
        [
            BotCommand("search", "Search for a book"),
            BotCommand("s", "Search for a book (short)"),
            BotCommand("fast", "Queue the top result immediately"),
            BotCommand("send", "Like /fast, but send the file back here"),
            BotCommand("email", "Search, pick, and email via Grimmory"),
            BotCommand("status", "Check download queue status"),
            BotCommand("help", "Show help message"),
        ]
    )


async def post_shutdown(application: Application) -> None:
    """Cleanup on shutdown."""
    import bot.state
    if bot.state.shelfmark:
        await bot.state.shelfmark.close()
    if bot.state.grimmory:
        await bot.state.grimmory.close()
    logger.info("HTTP clients closed.")


async def help_command(update: Update, context) -> None:
    """Handle /help and /start commands."""
    text = (
        "📚 <b>Shelfmark Bot</b>\n\n"
        "Search and download books from your Shelfmark instance.\n\n"
        "<b>Commands:</b>\n"
        "/search &lt;query&gt; — Search for a book\n"
        "/s &lt;query&gt; — Short alias for search\n"
        "/fast &lt;query&gt; — Queue the top result immediately\n"
        "/send &lt;query&gt; — Like /fast, but the file is sent back to this chat\n"
        "/email &lt;query&gt; — Like /search, but the pick is emailed via Grimmory Quick Send\n"
        "/status — Check download queue\n"
        "/help — Show this message\n\n"
        "Or just send a book title as a message — same as /fast. "
        "Several titles, one per line, are queued in turn.\n"
        "Files are never sent back unless you use /send — fetch them via /status."
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")  # type: ignore[union-attr]


def main() -> None:
    cfg: Config = load_config()
    setup_logging(cfg.log_level)

    logger.info("Starting Shelfmark Bot …")
    logger.info("Shelfmark URL: %s", cfg.shelfmark_url)

    # Set up access control
    if cfg.allowed_user_ids:
        set_allowed_ids(cfg.allowed_user_ids)
        logger.info("Access restricted to user IDs: %s", cfg.allowed_user_ids)
    else:
        logger.info("Access control disabled – all users allowed.")

    # Initialise the Shelfmark HTTP client
    import bot.state
    bot.state.shelfmark = ShelfmarkClient(base_url=cfg.shelfmark_url)
    if cfg.grimmory_enabled:
        bot.state.grimmory = GrimmoryClient(
            cfg.grimmory_url, cfg.grimmory_username, cfg.grimmory_password
        )
        logger.info("Grimmory URL: %s (/email enabled)", cfg.grimmory_url)
    else:
        logger.info("Grimmory not configured – /email disabled.")

    # Build Application
    app = (
        ApplicationBuilder()
        .token(cfg.telegram_bot_token)
        .arbitrary_callback_data(True)
        .read_timeout(60)
        .write_timeout(120)
        .connect_timeout(30)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # --- Register handlers (order matters) ---

    # Commands
    app.add_handler(CommandHandler(["search", "s"], search_command))
    app.add_handler(CommandHandler("fast", fast_command))
    app.add_handler(CommandHandler("send", send_command))
    app.add_handler(CommandHandler("email", email_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler(["help", "start"], help_command))

    # Callback queries (pattern-matched on the string prefix)
    app.add_handler(CallbackQueryHandler(download_callback, pattern=r"^dl:"))
    app.add_handler(
        CallbackQueryHandler(confirm_download_callback, pattern=r"^confirm_dl:")
    )
    app.add_handler(
        CallbackQueryHandler(cancel_download_callback, pattern=r"^cancel_dl")
    )
    app.add_handler(
        CallbackQueryHandler(refresh_status_callback, pattern=r"^refresh_status")
    )
    app.add_handler(
        CallbackQueryHandler(send_file_callback, pattern=r"^get_file:")
    )

    # Plain text messages → search (must be last)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text_search)
    )

    logger.info("Bot is starting (long-polling mode) …")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
