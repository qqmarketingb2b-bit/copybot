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

async def stream_claude(system, messages):
    reply = ""
    with anthropic_client.messages.stream(model=CLAUDE_MODEL, max_tokens=MAX_TOKENS, system=system, messages=messages) as stream:
        for text in stream.text_stream:
            reply += text
    return reply


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

    await update.message.reply_text("👋 Привет! Это бот для копирайтеров.\n\nВведи код доступа:")
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
        await safe_edit(query, f"🏠 Главное меню\n\nРоль: {ROLE_LABELS.get(role, role)}", reply_markup=kb_main_menu(is_admin_role(role)))
        return ST_MAIN_MENU

    if action == "write":
        projects = list_projects()
        if not projects:
            await safe_edit(query, "⚠️ Пока нет ни одного проекта.", reply_markup=kb_main_menu(is_admin_role(user["role"])))
            return ST_MAIN_MENU
        await safe_edit(query, "📁 Выбери проект для новой задачи:", reply_markup=kb_projects())
        return ST_WAIT_PROJECT

    if action == "tasks":
        await safe_edit(query, "📋 Твои задачи:", reply_markup=kb_tasks_list(uid))
        return ST_TASKS_MENU

    if action == "admin":
        if not is_admin_role(user["role"]):
            await safe_edit(query, "⛔ Нет доступа.")
            return ST_MAIN_MENU
        await safe_edit(query, "⚙️ Панель администратора:", reply_markup=kb_admin_menu())
        return ST_ADMIN_MENU

    return ST_MAIN_MENU


# ── Tasks list / open ────────────────────────────────────────────────

async def cb_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    uid   = query.from_user.id

    if parts[1] == "open":
        task_id = int(parts[2])
        task    = get_task(task_id)
        if not task or task["telegram_id"] != uid:
            await query.answer("Задача не найдена", show_alert=True)
            return ST_TASKS_MENU
        proj = get_project(task["project_id"]) if task["project_id"] else None
        fmt  = get_format(task["format_id"]) if task["format_id"] else None
        last_text = ""
        for msg in reversed(task["history"]):
            if msg["role"] == "assistant":
                last_text = msg["content"][:500]
                break
        status_label = STATUS_LABELS.get(task["status"], task["status"])
        preview = f"\n\n📝 Последний текст:\n{last_text}{'…' if last_text and len(last_text) >= 500 else ''}" if last_text else "\n\nЕщё нет сгенерированного текста — продолжи диалог, чтобы написать ТЗ."
        await safe_edit(
            query,
            f"{status_label}\nПроект: *{proj['name'] if proj else '—'}*\nФормат: {fmt['emoji'] if fmt else ''} {fmt['name'] if fmt else '—'}{preview}",
            parse_mode="Markdown",
            reply_markup=kb_task_open(task)
        )
        return ST_TASKS_MENU

    if parts[1] == "continue":
        task_id = int(parts[2])
        task    = get_task(task_id)
        if not task or task["telegram_id"] != uid:
            await query.answer("Задача не найдена", show_alert=True)
            return ST_TASKS_MENU
        set_active_task(uid, task_id)
        if not task["history"]:
            await safe_edit(query, "✏️ Напиши ТЗ — что нужно написать, о чём, ключевые тезисы:")
            return ST_WAIT_TZ
        await safe_edit(query, "💬 Продолжай — напиши правку или уточнение к этой задаче:")
        return ST_CHATTING

    if parts[1] == "saveex":
        task_id = int(parts[2])
        task    = get_task(task_id)
        if not task or task["telegram_id"] != uid:
            await query.answer("Задача не найдена", show_alert=True)
            return ST_TASKS_MENU
        last_text = None
        for msg in reversed(task["history"]):
            if msg["role"] == "assistant":
                last_text = msg["content"]
                break
        if not last_text:
            await query.answer("Нет текста для сохранения", show_alert=True)
            return ST_TASKS_MENU
        proj  = get_project(task["project_id"])
        fmt   = get_format(task["format_id"])
        uname = query.from_user.username or str(uid)
        fname = f"approved_{uname}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        add_example(task["project_id"], task["format_id"], fname, last_text)
        update_task(task_id, status="approved")
        await query.answer("✅ Сохранено как пример!")
        await safe_edit(
            query,
            f"✅ Текст сохранён как пример для проекта «{proj['name']}», формат «{fmt['name']}».\nЗадача отмечена как одобренная.",
            reply_markup=kb_tasks_list(uid)
        )
        return ST_TASKS_MENU

    if parts[1] == "delete":
        task_id = int(parts[2])
        task    = get_task(task_id)
        if task and task["telegram_id"] == uid:
            delete_task(task_id)
        await safe_edit(query, "🗑 Задача удалена.", reply_markup=kb_tasks_list(uid))
        return ST_TASKS_MENU

    return ST_TASKS_MENU


# ── New task: project → format → TZ ──────────────────────────────────

async def cb_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer()
    project_id = int(query.data.split(":")[1])
    proj       = get_project(project_id)
    formats    = get_project_formats(project_id)

    if not formats:
        await safe_edit(query, f"⚠️ У проекта «{proj['name']}» нет форматов. Обратись к администратору.", reply_markup=kb_projects())
        return ST_WAIT_PROJECT

    context.user_data["new_task_project_id"] = project_id
    await safe_edit(
        query,
        f"✅ Проект: *{proj['name']}*\n\nВыбери формат текста:",
        parse_mode="Markdown",
        reply_markup=kb_formats(project_id)
    )
    return ST_WAIT_FORMAT


async def cb_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query     = update.callback_query
    await query.answer()
    format_id = int(query.data.split(":")[1])
    fmt       = get_format(format_id)
    uid       = query.from_user.id
    pid       = context.user_data.get("new_task_project_id")

    task_id = create_task(uid, project_id=pid, format_id=format_id)
    set_active_task(uid, task_id)

    await safe_edit(
        query,
        f"✅ Формат: *{fmt['emoji']} {fmt['name']}*\n\n✏️ Напиши ТЗ — что нужно написать, о чём, ключевые тезисы:\n\n"
        "💡 Это новая задача — твои другие задачи остаются доступны в «Мои задачи».",
        parse_mode="Markdown"
    )
    return ST_WAIT_TZ


async def handle_tz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    task_id = get_active_task_id(uid)
    task    = get_task(task_id) if task_id else None

    if not task or not task.get("project_id") or not task.get("format_id"):
        await update.message.reply_text("⚠️ Сначала выбери проект и формат.", reply_markup=kb_main_menu(False))
        return ST_MAIN_MENU

    history = task["history"]
    history.append({"role": "user", "content": update.message.text})
    system   = build_system_prompt(task["project_id"], task["format_id"])
    thinking = await update.message.reply_text("⏳ Пишу текст...")

    try:
        reply = await stream_claude(system, history)
    except Exception as e:
        await thinking.edit_text(f"❌ Ошибка API: {e}")
        return ST_WAIT_TZ

    history.append({"role": "assistant", "content": reply})
    update_task(task_id, history=history, status="active")
    await thinking.delete()
    await update.message.reply_text(reply, reply_markup=kb_after_text(task_id))
    return ST_CHATTING


async def handle_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    task_id = get_active_task_id(uid)
    task    = get_task(task_id) if task_id else None

    if not task:
        await update.message.reply_text("⚠️ Активная задача не найдена.", reply_markup=kb_main_menu(False))
        return ST_MAIN_MENU

    history = task["history"]
    history.append({"role": "user", "content": update.message.text})
    system   = build_system_prompt(task["project_id"], task["format_id"])
    thinking = await update.message.reply_text("✏️ Вношу правки...")

    try:
        reply = await stream_claude(system, history)
    except Exception as e:
        await thinking.edit_text(f"❌ Ошибка API: {e}")
        return ST_CHATTING

    history.append({"role": "assistant", "content": reply})
    update_task(task_id, history=history)
    await thinking.delete()
    await update.message.reply_text(reply, reply_markup=kb_after_text(task_id))
    return ST_CHATTING


# ── Translation & SEO ────────────────────────────────────────────────

async def cb_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    uid   = query.from_user.id

    if parts[1] == "menu":
        task_id = int(parts[2])
        await safe_edit(query, "🌍 Выбери язык перевода:", reply_markup=kb_translate_languages(task_id))
        return ST_WAIT_TRANSLATE_LANG

    if parts[1] == "lang":
        task_id, lang_code = int(parts[2]), parts[3]
        task = get_task(task_id)
        fmt  = get_format(task["format_id"]) if task else None

        if fmt and fmt.get("is_article"):
            flag, lang_name, _ = LANGUAGES[lang_code]
            await safe_edit(
                query,
                f"{flag} Перевод на {lang_name}.\n\nЭто статья — хочешь добавить SEO-оптимизацию под этот язык и рынок?",
                reply_markup=kb_seo_choice(task_id, lang_code)
            )
            return ST_WAIT_SEO_CHOICE
        else:
            return await do_translation(update, context, task_id, lang_code, with_seo=False)

    if parts[1] == "go":
        task_id, lang_code, seo_flag = int(parts[2]), parts[3], parts[4]
        return await do_translation(update, context, task_id, lang_code, with_seo=(seo_flag == "seo"))

    return ST_CHATTING


async def do_translation(update, context, task_id, lang_code, with_seo):
    query = update.callback_query
    task  = get_task(task_id)
    if not task:
        await query.answer("Задача не найдена", show_alert=True)
        return ST_TASKS_MENU

    last_text = None
    for msg in reversed(task["history"]):
        if msg["role"] == "assistant":
            last_text = msg["content"]
            break

    if not last_text:
        await query.answer("Нет текста для перевода", show_alert=True)
        return ST_CHATTING

    flag, lang_name, _ = LANGUAGES[lang_code]
    await safe_edit(query, f"{flag} Перевожу на {lang_name}{' с SEO-оптимизацией' if with_seo else ''}...")

    system = build_translate_prompt(lang_code, task["project_id"], with_seo=with_seo)
    try:
        translated = await stream_claude(system, [{"role": "user", "content": last_text}])
    except Exception as e:
        await query.message.reply_text(f"❌ Ошибка API: {e}")
        return ST_CHATTING

    await query.message.reply_text(
        f"{flag} *{lang_name}*\n\n{translated}",
        parse_mode="Markdown",
        reply_markup=kb_after_translation(task_id)
    )
    return ST_CHATTING


async def cb_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles generic action callbacks, currently used for skipping TOV during project creation."""
    query  = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "skip":
        flow = context.user_data.get("admin_flow")
        if flow == "add_project":
            name    = context.user_data.get("new_project_name")
            new_pid = create_project(name, tov_text="", tov_filename="")
            context.user_data["edit_project_id"] = new_pid
            context.user_data["admin_flow"]      = None
            await query.message.reply_text(
                f"✅ Проект «{name}» создан без TOV.\n\nВыбери форматы для этого проекта (можно несколько):",
                reply_markup=kb_project_formats(new_pid)
            )
            return ST_EDIT_PROJECT_FORMAT_MENU
        return ST_ADMIN_MENU

    return ST_ADMIN_MENU


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
    query   = update.callback_query
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


# ── Users ─────────────────────────────────────────────────────────────

@require_admin
async def cb_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if parts[1] == "add":
        await safe_edit(query, "👤 Введи Telegram @username сотрудника (без @):\n\n⚠️ Сотрудник должен сначала написать боту /start.", reply_markup=kb_cancel("admin:users"))
        return ST_ADD_USER_WAIT_USERNAME

    if parts[1] == "manage":
        tid = int(parts[2])
        usr = get_user(tid)
        if not usr:
            await safe_edit(query, "❌ Пользователь не найден.", reply_markup=kb_users_menu())
            return ST_ADMIN_MENU
        uname = f"@{usr['username']}" if usr["username"] else str(tid)
        await safe_edit(query, f"👤 {uname}\nРоль: {ROLE_LABELS.get(usr['role'], usr['role'])}", reply_markup=kb_user_manage(tid, usr["role"]))
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
    row  = conn.execute("SELECT telegram_id, role FROM users WHERE username=? OR telegram_id=?", (text, text if text.isdigit() else -1)).fetchone()
    conn.close()

    if row and row[1] != "pending":
        await update.message.reply_text("⚠️ Этот пользователь уже есть в боте.", reply_markup=kb_users_menu())
        return ST_ADMIN_MENU

    if not row:
        await update.message.reply_text(f"⚠️ @{text} ещё не писал боту. Попроси написать /start.", reply_markup=kb_users_menu())
        return ST_ADMIN_MENU

    actor   = get_user(update.effective_user.id)
    buttons = [[InlineKeyboardButton("👤 Сотрудник", callback_data=f"newuser:role:{text}:employee")]]
    if actor and actor["role"] == ROLE_ADMIN:
        buttons.append([InlineKeyboardButton("⭐ Суб-Админ", callback_data=f"newuser:role:{text}:subadmin")])
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="admin:users")])
    await update.message.reply_text(f"Выбери роль для @{text}:", reply_markup=InlineKeyboardMarkup(buttons))
    return ST_ADD_USER_WAIT_ROLE


async def cb_newuser_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, ref, role = query.data.split(":")

    conn = get_conn()
    if ref.isdigit():
        tid   = int(ref)
        row   = conn.execute("SELECT username FROM users WHERE telegram_id=?", (tid,)).fetchone()
        uname = row[0] if row else None
    else:
        row = conn.execute("SELECT telegram_id FROM users WHERE username=?", (ref,)).fetchone()
        if not row:
            conn.close()
            await safe_edit(query, f"⚠️ @{ref} не найден.", reply_markup=kb_users_menu())
            return ST_ADMIN_MENU
        tid   = row[0]
        uname = ref
    conn.close()

    add_user(tid, uname or ref, role=role, added_by=query.from_user.id)
    await safe_edit(query, f"✅ @{uname or ref} добавлен как {ROLE_LABELS[role]}.", reply_markup=kb_users_menu())
    return ST_ADMIN_MENU


# ── Projects ──────────────────────────────────────────────────────────

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
        fmts = get_project_formats(pid)
        tov_info = "✅ Загружен" if proj["tov_text"] else "❌ Не задан"
        await safe_edit(query, f"📁 *{proj['name']}*\n\nTOV: {tov_info}\nФорматов: {len(fmts)}", parse_mode="Markdown", reply_markup=kb_project_edit(pid))
        context.user_data["edit_project_id"] = pid
        return ST_EDIT_PROJECT_MENU

    if parts[1] == "edittov":
        pid = int(parts[2])
        context.user_data["edit_project_id"] = pid
        await safe_edit(query, "✏️ Отправь новый TOV — текстом или файлом (PDF, DOCX, TXT).", reply_markup=kb_cancel(f"proj:edit:{pid}"))
        return ST_EDIT_PROJECT_TOV

    if parts[1] == "formats":
        pid = int(parts[2])
        context.user_data["edit_project_id"] = pid
        await safe_edit(query, "📝 Форматы проекта (✅ — подключён).\n\nНажми чтобы включить/выключить:", reply_markup=kb_project_formats(pid))
        return ST_EDIT_PROJECT_FORMAT_MENU

    if parts[1] == "togglefmt":
        pid, fid = int(parts[2]), int(parts[3])
        if is_format_linked(pid, fid):
            unlink_project_format(pid, fid)
        else:
            link_project_format(pid, fid)
        await safe_edit(query, "📝 Форматы проекта (✅ — подключён):\n\nНажми чтобы включить/выключить:", reply_markup=kb_project_formats(pid))
        return ST_EDIT_PROJECT_FORMAT_MENU

    if parts[1] == "exmenu":
        pid  = int(parts[2])
        fmts = get_project_formats(pid)
        if not fmts:
            await query.answer("Сначала подключи хотя бы один формат", show_alert=True)
            return ST_EDIT_PROJECT_FORMAT_MENU
        await safe_edit(query, "📄 Выбери формат чтобы управлять примерами:", reply_markup=kb_project_format_examples(pid))
        return ST_EDIT_PROJECT_FORMAT_MENU

    if parts[1] == "exfmt":
        pid, fid = int(parts[2]), int(parts[3])
        fmt  = get_format(fid)
        exs  = get_examples(pid, fid)
        context.user_data["edit_project_id"] = pid
        context.user_data["edit_format_id"]  = fid
        await safe_edit(query, f"📄 Примеры для «{fmt['name']}» (всего: {len(exs)}):", reply_markup=kb_format_examples(pid, fid))
        return ST_EDIT_PROJECT_FORMAT_MENU

    if parts[1] == "addex":
        pid, fid = int(parts[2]), int(parts[3])
        fmt = get_format(fid)
        context.user_data["edit_project_id"] = pid
        context.user_data["edit_format_id"]  = fid
        await safe_edit(query, f"📎 Загрузи файлы с примерами для формата «{fmt['name']}» (PDF, DOCX, TXT).\n\nКогда закончишь — нажми «Готово».",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Готово", callback_data=f"proj:exfmt:{pid}:{fid}")]]))
        return ST_EDIT_PROJECT_EXAMPLES

    if parts[1] == "delex":
        ex_id, pid, fid = int(parts[2]), int(parts[3]), int(parts[4])
        delete_example(ex_id)
        await query.answer("Пример удалён")
        fmt = get_format(fid)
        exs = get_examples(pid, fid)
        await safe_edit(query, f"📄 Примеры для «{fmt['name']}» (всего: {len(exs)}):", reply_markup=kb_format_examples(pid, fid))
        return ST_EDIT_PROJECT_FORMAT_MENU

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
        await update.message.reply_text("⚠️ Проект с таким названием уже существует:")
        return ST_ADD_PROJECT_NAME
    context.user_data["new_project_name"] = name
    await update.message.reply_text(
        f"✅ Проект: *{name}*\n\nВведи TOV — описание голоса и тона бренда.\n\nМожно текстом или файлом (PDF, DOCX, TXT).",
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
            "✅ TOV сохранён!\n\nТеперь выбери форматы для этого проекта (✅ — подключён):",
            reply_markup=kb_project_formats(new_pid)
        )
        return ST_EDIT_PROJECT_FORMAT_MENU
    else:
        update_project(pid, tov_text=tov, tov_filename=fname)
        proj = get_project(pid)
        await update.message.reply_text(f"✅ TOV проекта «{proj['name']}» обновлён.", reply_markup=kb_project_edit(pid))
        return ST_EDIT_PROJECT_MENU


async def handle_project_example_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pid = context.user_data.get("edit_project_id")
    fid = context.user_data.get("edit_format_id")

    if not update.message.document:
        await update.message.reply_text("Отправь файл (PDF, DOCX, TXT) или нажми «Готово».")
        return ST_EDIT_PROJECT_EXAMPLES

    doc    = update.message.document
    tfile  = await doc.get_file()
    fbytes = await tfile.download_as_bytearray()
    text   = await extract_text_from_file(bytes(fbytes), doc.file_name)
    add_example(pid, fid, doc.file_name, text)
    exs = get_examples(pid, fid)
    fmt = get_format(fid)
    await update.message.reply_text(
        f"✅ Пример «{doc.file_name}» добавлен в «{fmt['name']}». Всего: {len(exs)}\n\nПрисылай ещё или нажми «Готово».",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Готово", callback_data=f"proj:exfmt:{pid}:{fid}")]]))
    return ST_EDIT_PROJECT_EXAMPLES


# ── Formats ───────────────────────────────────────────────────────────

@require_admin
async def cb_fmt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if parts[1] == "add":
        context.user_data["admin_flow"] = "add_format"
        await safe_edit(query, "📝 Введи название нового формата:", reply_markup=kb_cancel("admin:formats"))
        return ST_ADD_FORMAT_NAME

    if parts[1] == "manage":
        fid = int(parts[2])
        fmt = get_format(fid)
        article_label = "Да (с поддержкой SEO)" if fmt.get("is_article") else "Нет"
        await safe_edit(query, f"{fmt['emoji']} *{fmt['name']}*\n\n{fmt['instruction']}\n\nЭто формат статьи: {article_label}", parse_mode="Markdown", reply_markup=kb_format_manage(fid))
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
    await update.message.reply_text("Введи эмодзи для формата (например 🗞):", reply_markup=kb_cancel("admin:formats"))
    return ST_ADD_FORMAT_EMOJI

async def handle_add_format_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_format_emoji"] = update.message.text.strip()[:2]
    await update.message.reply_text("Напиши инструкцию для Claude — структура, длина, стиль:", reply_markup=kb_cancel("admin:formats"))
    return ST_ADD_FORMAT_INSTRUCTION

async def handle_add_format_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_format_instruction"] = update.message.text.strip()
    await update.message.reply_text(
        "Это формат статьи? Если да — при переводе будет предложена SEO-оптимизация под целевой язык.",
        reply_markup=kb_article_yesno()
    )
    return ST_ADD_FORMAT_INSTRUCTION


async def cb_newformat_article(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    is_article = 1 if query.data.endswith("yes") else 0

    name        = context.user_data.get("new_format_name", "Новый формат")
    emoji       = context.user_data.get("new_format_emoji", "📝")
    instruction = context.user_data.get("new_format_instruction", "")
    create_format(name, emoji, instruction, is_article=is_article)
    context.user_data["admin_flow"] = None
    await safe_edit(query, f"✅ Формат «{emoji} {name}» добавлен!", reply_markup=kb_formats_menu())
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
    await update.message.reply_text("Не понимаю. Выбери действие:", reply_markup=kb_main_menu(is_admin_role(user["role"])))
    return ST_MAIN_MENU
