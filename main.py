import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters
)

from config import TELEGRAM_TOKEN, ANTHROPIC_KEY
from database import init_db
from handlers import *

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def build_app():
    app  = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            ST_WAIT_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code),
            ],
            ST_MAIN_MENU: [
                CallbackQueryHandler(cb_menu, pattern="^menu:"),
            ],
            ST_WAIT_PROJECT: [
                CallbackQueryHandler(cb_project, pattern="^project:"),
                CallbackQueryHandler(cb_menu,    pattern="^menu:"),
            ],
            ST_WAIT_FORMAT: [
                CallbackQueryHandler(cb_format, pattern="^format:"),
                CallbackQueryHandler(cb_menu,   pattern="^menu:"),
            ],
            ST_WAIT_TZ: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tz),
                CallbackQueryHandler(cb_menu, pattern="^menu:"),
            ],
            ST_CHATTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit),
                CallbackQueryHandler(cb_action,  pattern="^action:"),
                CallbackQueryHandler(cb_menu,    pattern="^menu:"),
                CallbackQueryHandler(cb_project, pattern="^project:"),
                CallbackQueryHandler(cb_format,  pattern="^format:"),
            ],
            ST_ADMIN_MENU: [
                CallbackQueryHandler(cb_admin,       pattern="^admin:"),
                CallbackQueryHandler(cb_user,        pattern="^user:"),
                CallbackQueryHandler(cb_proj,        pattern="^proj:"),
                CallbackQueryHandler(cb_fmt,         pattern="^fmt:"),
                CallbackQueryHandler(cb_menu,        pattern="^menu:"),
                CallbackQueryHandler(cb_newuser_role,pattern="^newuser:"),
            ],
            ST_ADD_USER_WAIT_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_user_username),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
            ],
            ST_ADD_USER_WAIT_ROLE: [
                CallbackQueryHandler(cb_newuser_role, pattern="^newuser:"),
                CallbackQueryHandler(cb_admin,        pattern="^admin:"),
            ],
            ST_ADD_PROJECT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_project_name),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
            ],
            ST_ADD_PROJECT_TOV: [
                MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.Document.ALL, handle_project_tov_text),
                CallbackQueryHandler(cb_admin,  pattern="^admin:"),
                CallbackQueryHandler(cb_action, pattern="^action:skip"),
            ],
            ST_ADD_PROJECT_FORMATS: [
                CallbackQueryHandler(cb_proj,  pattern="^proj:"),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
            ],
            ST_ADD_PROJECT_EXAMPLES: [
                MessageHandler(filters.Document.ALL, handle_project_example_file),
                CallbackQueryHandler(cb_proj,  pattern="^proj:"),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
            ],
            ST_EDIT_PROJECT_MENU: [
                CallbackQueryHandler(cb_proj,  pattern="^proj:"),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
                CallbackQueryHandler(cb_menu,  pattern="^menu:"),
            ],
            ST_EDIT_PROJECT_TOV: [
                MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.Document.ALL, handle_project_tov_text),
                CallbackQueryHandler(cb_proj,  pattern="^proj:"),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
            ],
            ST_EDIT_PROJECT_FORMAT_MENU: [
                CallbackQueryHandler(cb_proj,  pattern="^proj:"),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
                CallbackQueryHandler(cb_menu,  pattern="^menu:"),
            ],
            ST_EDIT_PROJECT_EXAMPLES: [
                MessageHandler(filters.Document.ALL, handle_project_example_file),
                CallbackQueryHandler(cb_proj,  pattern="^proj:"),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
            ],
            ST_ADD_FORMAT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_format_name),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
            ],
            ST_ADD_FORMAT_EMOJI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_format_emoji),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
            ],
            ST_ADD_FORMAT_INSTRUCTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_format_instruction),
                CallbackQueryHandler(cb_admin, pattern="^admin:"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("start",  cmd_start),
            MessageHandler(filters.ALL, unknown_message),
        ],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(conv)
    return app


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    if not ANTHROPIC_KEY:
        raise ValueError("ANTHROPIC_API_KEY не задан!")
    init_db()
    logger.info("База данных инициализирована")
    app = build_app()
    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
