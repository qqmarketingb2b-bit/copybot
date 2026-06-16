from datetime import datetime
from anthropic import Anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from config import *
from database import *
from utils import *

anthropic_client = Anthropic(api_key=ANTHROPIC_KEY)


# ── Helpers ───────────────────────────────────────────────────────────

def is_admin_role(role):
    return role in ADMIN_ROLES

async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)


# ── Entry point ───────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    uname = update.effective_user.username or str(uid)
    user  = get_user(uid)

    if not user:
        conn = get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, role, added_at) VALUES (?,?,?,?)",
            (uid, uname, "pending", datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        user = get_user(uid)

    if user and user["role"] != "pending":
        role  = user["role"]
        name  = update.effective_user.first_name or "коллега"
        label = ROLE_LABELS.get(role, role)
        await update.message.reply_text(
            f"👋 С возвращением, {name}!\n\nТвоя роль: {label}",
            reply_markup=kb_main_menu(is_admin_role(role))
        )
        return ST_MAIN_MENU

    await update.message.reply_text(
        "👋 Привет! Это бот для копирайтеров.\n\nВведи код доступа:"
    )
    return ST_WAIT_CODE


async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    code  = update.message.text.strip()
    uname = update.effective_user.username or str(uid)

    if code == ADMIN_CODE:
        add_user(uid, uname, role=ROLE_ADMIN)
        await update.message.reply_text(
            "✅ Код принят. Ты вошёл как *Администратор*.",
            parse_mode="Markdown",
            reply_markup=kb_main_menu(True)
        )
        return ST_MAIN_MENU

    await update.message.reply_text("❌ Неверный код. Попробуй ещё раз:")
    return ST_WAIT_CODE


# ── Main menu ─────────────────────────────────────────────────────────

async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = query.from_user.id
    user = get_user(uid)
    if not user or user["role"] == "pending":
        await safe_edit(query, "❌ Нет доступа. Введи /start")
        return ST_WAIT_CODE

    action = query.data.split(":", 1)[1]

    if action == "main":
        role = user["role"]
        await safe_edit(
            query,
            f"🏠 Главное меню\n\nРоль: {ROLE_LABELS.get(role, role)}",
            reply_markup=kb_main_menu(is_admin_role(role))
        )
        return ST_MAIN_MENU

    if action == "write":
        projects = list_projects()
        if not projects:
            await safe_edit(query, "⚠️ Пока нет ни одного проекта. Обратись к администратору.", reply_markup=kb_main_menu(is_admin_role(user["role"])))
            return ST_MAIN_MENU
        await safe_edit(query, "📁 Выбери проект:", reply_markup=kb_projects())
        return ST_WAIT_PROJECT

    if action == "admin":
        if not is_admin_role(user["role"]):
            await safe_edit(query, "⛔ Нет доступа.")
            return ST_MAIN_MENU
        await safe_edit(query, "⚙️ Панель администратора:", reply_markup=kb_admin_menu())
        return ST_ADMIN_MENU

    return ST_MAIN_MENU


# ── Writing flow ──────────────────────────────────────────────────────

async def cb_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    project_id = int(query.data.split(":")[1])
    proj = get_project(project_id)
    save_session(query.from_user.id, project_id=project_id)
    clear_session_history(query.from_user.id)
    await safe_edit(
        query,
        f"✅ Проект: *{proj['name']}*\n\nВыбери формат текста:",
        parse_mode="Markdown",
        reply_markup=kb_formats()
    )
    return ST_WAIT_FORMAT


async def cb_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    format_id = int(query.data.split(":")[1])
    fmt = get_format(format_id)
    save_session(query.from_user.id, format_id=format_id)
    clear_session_history(query.from_user.id)
    await safe_edit(
        query,
        f"✅ Формат: *{fmt['emoji']} {fmt['name']}*\n\n✏️ Напиши ТЗ — что нужно написать, о чём, ключевые тезисы:",
        parse_mode="Markdown"
    )
    return ST_WAIT_TZ


async def handle_tz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    session = get_session(uid)

    if not session.get("project_id") or not session.get("format_id"):
        await update.message.reply_text("⚠️ Сначала выбери проект и формат.", reply_markup=kb_main_menu(False))
        return ST_MAIN_MENU

    history = session["history"]
    history.append({"role": "user", "content": update.message.text})

    system   = build_system_prompt(session["project_id"], session["format_id"])
    thinking = await update.message.reply_text("⏳ Пишу текст...")

    try:
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL, max_tokens=MAX_TOKENS,
            system=system, messages=history
        )
        reply = resp.content[0].text
    except Exception as e:
        await thinking.edit_text(f"❌ Ошибка API: {e}")
        return ST_WAIT_TZ

    history.append({"role": "assistant", "content": reply})
    save_session(uid, history=history)
    await thinking.delete()
    await update.message.reply_text(reply, reply_markup=kb_after_text())
    return ST_CHATTING


async def handle_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    session = get_session(uid)

    history = session["history"]
    history.append({"role": "user", "content": update.message.text})

    system   = build_system_prompt(session["project_id"], session["format_id"])
    thinking = await update.message.reply_text("✏️ Вношу правки...")

    try:
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL, max_tokens=MAX_TOKENS,
            system=system, messages=history
        )
        reply = resp.content[0].text
    except Exception as e:
        await thinking.edit_text(f"❌ Ошибка API: {e}")
        return ST_CHATTING

    history.append({"role": "assistant", "content": reply})
    save_session(uid, history=history)
    await thinking.delete()
    await update.message.reply_text(reply, reply_markup=kb_after_text())
    return ST_CHATTING


async def cb_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "new_tz":
        clear_session_history(query.from_user.id)
        await safe_edit(query, "✏️ Напиши новое ТЗ:")
        return ST_WAIT_TZ

    if action == "skip":
        context.user_data["skip"] = True
        return None

    return ST_CHATTING


# ══════════════════════════════════════════════════════════════════════
# ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════

def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid  = update.effective_user.id
        user = get_user(uid)
        if not user or not is_admin_role(user["role"]):
            if update.callback_query:
                await update.callback_query.answer("⛔ Нет доступа", show_alert=True)
            return ST_MAIN_MENU
        return await func(update, context)
    return wrapper


@require_admin
async def cb_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    section = query.data.split(":", 1)[1]

    if section == "back":
        await safe_edit(query, "⚙️ Панель администратора:", reply_markup=kb_admin_menu())
        return ST_ADMIN_MENU

    if section == "users":
        await safe_edit(query, "👥 Пользователи бота:", reply_markup=kb_users_menu())
        return ST_ADMIN_MENU

    if section == "projects":
        await safe_edit(query, "📁 Проекты:", reply_markup=kb_projects_menu())
        return ST_ADMIN_MENU

    if section == "formats":
        await safe_edit(query, "📝 Форматы текстов:", reply_markup=kb_formats_menu())
        return ST_ADMIN_MENU

    return ST_ADMIN_MENU


# ── Users management ──────────────────────────────────────────────────

@require_admin
async def cb_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if parts[1] == "add":
        context.user_data["admin_flow"] = "add_user"
        await safe_edit(
            query,
            "👤 Введи Telegram @username сотрудника (без @):\n\n"
            "⚠️ Сотрудник должен сначала написать боту /start, чтобы мы знали его ID.\n"
            "Либо введи числовой Telegram ID напрямую.",
            reply_markup=kb_cancel("admin:users")
        )
        return ST_ADD_USER_WAIT_USERNAME

    if parts[1] == "manage":
        tid  = int(parts[2])
        usr  = get_user(tid)
        if not usr:
            await safe_edit(query, "❌ Пользователь не найден.", reply_markup=kb_users_menu())
            return ST_ADMIN_MENU
        uname = f"@{usr['username']}" if usr["username"] else str(tid)
        label = ROLE_LABELS.get(usr["role"], usr["role"])
        await safe_edit(
            query,
            f"👤 {uname}\nРоль: {label}",
            reply_markup=kb_user_manage(tid, usr["role"])
        )
        return ST_ADMIN_MENU

    if parts[1] == "setrole":
        tid, new_role = int(parts[2]), parts[3]
        actor = get_user(query.from_user.id)
        if actor["role"] != ROLE_ADMIN and new_role == ROLE_SUBADMIN:
            await query.answer("⛔ Только Администратор может назначать Суб-Админов.", show_alert=True)
            return ST_ADMIN_MENU
        update_user_role(tid, new_role)
        await safe_edit(query, f"✅ Роль обновлена: {ROLE_LABELS[new_role]}", reply_markup=kb_users_menu())
        return ST_ADMIN_MENU

    if parts[1] == "remove":
        tid    = int(parts[2])
        actor  = get_user(query.from_user.id)
        target = get_user(tid)
        if target and target["role"] == ROLE_ADMIN and actor["role"] != ROLE_ADMIN:
            await query.answer("⛔ Нельзя удалить Администратора.", show_alert=True)
            return ST_ADMIN_MENU
        remove_user(tid)
        await safe_edit(query, "🗑 Пользователь удалён.", reply_markup=kb_users_menu())
        return ST_ADMIN_MENU

    return ST_ADMIN_MENU


async def handle_add_user_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lstrip("@")
    conn = get_conn()
    row  = conn.execute(
        "SELECT telegram_id, role FROM users WHERE username=? OR telegram_id=?",
        (text, text if text.isdigit() else -1)
    ).fetchone()
    conn.close()

    if row and row[1] != "pending":
        await update.message.reply_text("⚠️ Этот пользователь уже есть в боте.", reply_markup=kb_users_menu())
        return ST_ADMIN_MENU

    if not row:
        await update.message.reply_text(
            f"⚠️ Пользователь @{text} ещё не писал боту.\n"
            "Попроси его написать /start боту, потом добавь снова.",
            reply_markup=kb_users_menu()
        )
        return ST_ADMIN_MENU

    context.user_data["new_user_ref"] = text
    await update.message.reply_text(
        f"Выбери роль для @{text}:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Сотрудник",  callback_data=f"newuser:role:{text}:employee")],
            [InlineKeyboardButton("⭐ Суб-Админ", callback_data=f"newuser:role:{text}:subadmin")],
            [InlineKeyboardButton("❌ Отмена",     callback_data="admin:users")],
        ])
    )
    return ST_ADD_USER_WAIT_ROLE


async def cb_newuser_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, ref, role = query.data.split(":")

    conn = get_conn()
    if ref.isdigit():
        tid  = int(ref)
        row  = conn.execute("SELECT username FROM users WHERE telegram_id=?", (tid,)).fetchone()
        uname = row[0] if row else None
    else:
        row = conn.execute("SELECT telegram_id FROM users WHERE username=?", (ref,)).fetchone()
        if not row:
            conn.close()
            await safe_edit(query, f"⚠️ @{ref} не найден. Пусть напишет /start боту.", reply_markup=kb_users_menu())
            return ST_ADMIN_MENU
        tid   = row[0]
        uname = ref
    conn.close()

    add_user(tid, uname or ref, role=role, added_by=query.from_user.id)
    await safe_edit(
        query,
        f"✅ @{uname or ref} добавлен как {ROLE_LABELS[role]}.",
        reply_markup=kb_users_menu()
    )
    return ST_ADMIN_MENU


# ── Projects management ───────────────────────────────────────────────

@require_admin
async def cb_proj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if parts[1] == "add":
        context.user_data["admin_flow"] = "add_project"
        await safe_edit(query, "📁 Введи название нового проекта:", reply_markup=kb_cancel("admin:projects"))
        return ST_ADD_PROJECT_NAME

    if parts[1] == "edit":
        pid  = int(parts[2])
        proj = get_project(pid)
        exs  = get_examples(pid)
        tov_info = "✅ Загружен" if proj["tov_text"] else "❌ Не задан"
        await safe_edit(
            query,
            f"📁 *{proj['name']}*\n\nTOV: {tov_info}\nПримеров текстов: {len(exs)}",
            parse_mode="Markdown",
            reply_markup=kb_project_edit(pid)
        )
        context.user_data["edit_project_id"] = pid
        return ST_EDIT_PROJECT_MENU

    if parts[1] == "edittov":
        pid = int(parts[2])
        context.user_data["edit_project_id"] = pid
        await safe_edit(
            query,
            "✏️ Отправь новый TOV — текстом или загрузи файл (PDF, DOCX, TXT).",
            reply_markup=kb_cancel(f"proj:edit:{pid}")
        )
        return ST_EDIT_PROJECT_TOV

    if parts[1] == "addex":
        pid = int(parts[2])
        context.user_data["edit_project_id"] = pid
        exs = get_examples(pid)
        await safe_edit(
            query,
            f"📄 Загрузи файлы с примерами текстов (PDF, DOCX, TXT).\n\nСейчас примеров: {len(exs)}\n\nОтправляй по одному. Когда закончишь — нажми «Готово».",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Готово", callback_data=f"proj:edit:{pid}")],
            ])
        )
        return ST_EDIT_PROJECT_EXAMPLES

    if parts[1] == "listex":
        pid = int(parts[2])
        exs = get_examples(pid)
        if not exs:
            await query.answer("Примеров нет", show_alert=True)
            return ST_EDIT_PROJECT_MENU
        btns = [[InlineKeyboardButton(f"🗑 {e['filename']}", callback_data=f"proj:delex:{e['id']}:{pid}")] for e in exs]
        btns.append([InlineKeyboardButton("◀️ Назад", callback_data=f"proj:edit:{pid}")])
        await safe_edit(query, "📋 Примеры (нажми чтобы удалить):", reply_markup=InlineKeyboardMarkup(btns))
        return ST_EDIT_PROJECT_MENU

    if parts[1] == "delex":
        ex_id, pid = int(parts[2]), int(parts[3])
        delete_example(ex_id)
        await query.answer("Пример удалён")
        exs  = get_examples(pid)
        btns = [[InlineKeyboardButton(f"🗑 {e['filename']}", callback_data=f"proj:delex:{e['id']}:{pid}")] for e in exs]
        btns.append([InlineKeyboardButton("◀️ Назад", callback_data=f"proj:edit:{pid}")])
        await safe_edit(query, f"📋 Примеры (осталось {len(exs)}):", reply_markup=InlineKeyboardMarkup(btns))
        return ST_EDIT_PROJECT_MENU

    if parts[1] == "delete":
        pid  = int(parts[2])
        proj = get_project(pid)
        delete_project(pid)
        await safe_edit(query, f"🗑 Проект «{proj['name']}» удалён.", reply_markup=kb_projects_menu())
        return ST_ADMIN_MENU

    return ST_ADMIN_MENU


async def handle_add_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if get_project_by_name(name):
        await update.message.reply_text("⚠️ Проект с таким названием уже существует. Введи другое:")
        return ST_ADD_PROJECT_NAME
    context.user_data["new_project_name"] = name
    await update.message.reply_text(
        f"✅ Проект: *{name}*\n\nТеперь введи TOV — описание голоса и тона бренда.\n\nМожно написать текстом или прислать файл (PDF, DOCX, TXT).",
        parse_mode="Markdown",
        reply_markup=kb_skip_or_cancel("admin:projects")
    )
    return ST_ADD_PROJECT_TOV


async def handle_project_tov_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flow = context.user_data.get("admin_flow")
    pid  = context.user_data.get("edit_project_id")

    if update.message.document:
        doc    = update.message.document
        tfile  = await doc.get_file()
        fbytes = await tfile.download_as_bytearray()
        tov    = await extract_text_from_file(bytes(fbytes), doc.file_name)
        fname  = doc.file_name
    else:
        tov   = update.message.text.strip()
        fname = "текст"

    if flow == "add_project":
        name    = context.user_data.get("new_project_name")
        new_pid = create_project(name, tov_text=tov, tov_filename=fname)
        context.user_data["edit_project_id"] = new_pid
        context.user_data["admin_flow"]      = None
        await update.message.reply_text(
            "✅ TOV сохранён!\n\nТеперь можешь добавить примеры текстов (PDF, DOCX, TXT). Присылай по одному. Когда закончишь — нажми «Готово».",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Готово — открыть проект", callback_data=f"proj:edit:{new_pid}")],
            ])
        )
        return ST_EDIT_PROJECT_EXAMPLES
    else:
        update_project(pid, tov_text=tov, tov_filename=fname)
        proj = get_project(pid)
        await update.message.reply_text(
            f"✅ TOV проекта «{proj['name']}» обновлён.",
            reply_markup=kb_project_edit(pid)
        )
        return ST_EDIT_PROJECT_MENU


async def handle_project_example_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pid = context.user_data.get("edit_project_id")
    if not update.message.document:
        await update.message.reply_text("Отправь файл (PDF, DOCX, TXT) или нажми «Готово».")
        return ST_EDIT_PROJECT_EXAMPLES

    doc    = update.message.document
    tfile  = await doc.get_file()
    fbytes = await tfile.download_as_bytearray()
    text   = await extract_text_from_file(bytes(fbytes), doc.file_name)
    add_example(pid, doc.file_name, text)
    exs = get_examples(pid)
    await update.message.reply_text(
        f"✅ Пример «{doc.file_name}» добавлен. Всего: {len(exs)}\n\nПрисылай ещё или нажми «Готово».",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Готово", callback_data=f"proj:edit:{pid}")],
        ])
    )
    return ST_EDIT_PROJECT_EXAMPLES


# ── Formats management ────────────────────────────────────────────────

@require_admin
async def cb_fmt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if parts[1] == "add":
        context.user_data["admin_flow"] = "add_format"
        await safe_edit(query, "📝 Введи название нового формата (например: Пресс-релиз):", reply_markup=kb_cancel("admin:formats"))
        return ST_ADD_FORMAT_NAME

    if parts[1] == "manage":
        fid = int(parts[2])
        fmt = get_format(fid)
        await safe_edit(
            query,
            f"{fmt['emoji']} *{fmt['name']}*\n\n{fmt['instruction']}",
            parse_mode="Markdown",
            reply_markup=kb_format_manage(fid)
        )
        return ST_ADMIN_MENU

    if parts[1] == "delete":
        fid = int(parts[2])
        fmt = get_format(fid)
        delete_format(fid)
        await safe_edit(query, f"🗑 Формат «{fmt['name']}» удалён.", reply_markup=kb_formats_menu())
        return ST_ADMIN_MENU

    return ST_ADMIN_MENU


async def handle_add_format_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_format_name"] = update.message.text.strip()
    await update.message.reply_text("Введи эмодзи для этого формата (например 🗞):", reply_markup=kb_cancel("admin:formats"))
    return ST_ADD_FORMAT_EMOJI


async def handle_add_format_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_format_emoji"] = update.message.text.strip()[:2]
    await update.message.reply_text(
        "Напиши инструкцию для Claude — как писать в этом формате.\n\nНапример: структура, длина, стиль.",
        reply_markup=kb_cancel("admin:formats")
    )
    return ST_ADD_FORMAT_INSTRUCTION


async def handle_add_format_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name        = context.user_data.get("new_format_name", "Новый формат")
    emoji       = context.user_data.get("new_format_emoji", "📝")
    instruction = update.message.text.strip()
    create_format(name, emoji, instruction)
    context.user_data["admin_flow"] = None
    await update.message.reply_text(
        f"✅ Формат «{emoji} {name}» добавлен!",
        reply_markup=kb_formats_menu()
    )
    return ST_ADMIN_MENU


# ── Cancel / fallback ─────────────────────────────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    uid  = update.effective_user.id
    user = get_user(uid)
    await update.message.reply_text(
        "❌ Действие отменено.",
        reply_markup=kb_main_menu(is_admin_role(user["role"]) if user and user["role"] != "pending" else False)
    )
    return ST_MAIN_MENU if (user and user["role"] != "pending") else ST_WAIT_CODE


async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    user = get_user(uid)
    if not user or user["role"] == "pending":
        await update.message.reply_text("Введи /start для начала.")
        return ST_WAIT_CODE
    await update.message.reply_text(
        "Не понимаю. Выбери действие:",
        reply_markup=kb_main_menu(is_admin_role(user["role"]))
    )
    return ST_MAIN_MENU
