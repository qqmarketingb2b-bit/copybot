import io
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import (
    get_project, get_examples, get_format, list_projects, list_formats,
    list_users, get_project_formats, is_format_linked
)
from config import ROLE_LABELS, ROLE_ADMIN, ROLE_SUBADMIN, ROLE_EMPLOYEE


# ── Prompt builder ────────────────────────────────────────────────────

def build_system_prompt(project_id, format_id):
    proj     = get_project(project_id)
    fmt      = get_format(format_id)
    examples = get_examples(project_id, format_id)

    tov_block = proj["tov_text"].strip() if proj["tov_text"] else "Пиши в нейтральном профессиональном стиле."

    examples_block = ""
    if examples:
        examples_block = f"\n\nПримеры одобренных текстов в формате «{fmt['name']}» для этого проекта (придерживайся их стиля):\n"
        for i, ex in enumerate(examples[:5], 1):
            examples_block += f"\n--- Пример {i} ---\n{ex['content'][:2000]}\n"

    return f"""Ты — опытный копирайтер, работаешь над контентом для проекта «{proj['name']}».

═══ ТОН И ГОЛОС БРЕНДА (TOV) ═══
{tov_block}

═══ ФОРМАТ ЗАДАНИЯ ═══
{fmt['name']}
{fmt['instruction']}
{examples_block}

═══ ПРАВИЛА РАБОТЫ ═══
- Всегда строго придерживайся TOV проекта.
- Если пользователь просит правки — вноси их точечно, не переписывай текст целиком без прямого запроса.
- Если ТЗ неполное или непонятное — задай один уточняющий вопрос перед написанием.
- Отвечай только на русском языке, если в ТЗ не указано иное.
- Не добавляй никаких пояснений или комментариев после текста — только сам текст.
"""


# ── File text extractor ───────────────────────────────────────────────

async def extract_text_from_file(file_bytes, filename):
    fname = filename.lower()

    if fname.endswith(".txt"):
        for enc in ("utf-8", "cp1251", "latin-1"):
            try:
                return file_bytes.decode(enc)
            except Exception:
                continue
        return file_bytes.decode("utf-8", errors="replace")

    if fname.endswith(".pdf"):
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except ImportError:
            return "[PDF получен, но pypdf не установлен]"
        except Exception as e:
            return f"[Не удалось извлечь текст из PDF: {e}]"

    if fname.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            return "[DOCX получен, но python-docx не установлен]"
        except Exception as e:
            return f"[Не удалось извлечь текст из DOCX: {e}]"

    return f"[Формат {filename} не поддерживается. Используй TXT, PDF или DOCX]"


# ── Keyboards ─────────────────────────────────────────────────────────

def kb_main_menu(is_admin):
    buttons = [[InlineKeyboardButton("✍️ Создать текст", callback_data="menu:write")]]
    if is_admin:
        buttons.append([InlineKeyboardButton("⚙️ Панель администратора", callback_data="menu:admin")])
    return InlineKeyboardMarkup(buttons)

def kb_projects():
    projects = list_projects()
    buttons = [[InlineKeyboardButton(p["name"], callback_data=f"project:{p['id']}")] for p in projects]
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)

def kb_formats(project_id):
    formats = get_project_formats(project_id)
    buttons = [[InlineKeyboardButton(f"{f['emoji']} {f['name']}", callback_data=f"format:{f['id']}")] for f in formats]
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="menu:write")])
    return InlineKeyboardMarkup(buttons)

def kb_after_text():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Новое ТЗ", callback_data="action:new_tz"),
         InlineKeyboardButton("📁 Сменить проект", callback_data="menu:write")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")],
    ])

def kb_admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Пользователи",   callback_data="admin:users")],
        [InlineKeyboardButton("📁 Проекты",         callback_data="admin:projects")],
        [InlineKeyboardButton("📝 Форматы",         callback_data="admin:formats")],
        [InlineKeyboardButton("🏠 Главное меню",    callback_data="menu:main")],
    ])

def kb_users_menu():
    users = [u for u in list_users() if u["role"] != "pending"]
    buttons = []
    for u in users:
        label = f"{ROLE_LABELS.get(u['role'], u['role'])} · @{u['username'] or u['telegram_id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"user:manage:{u['telegram_id']}")])
    buttons.append([InlineKeyboardButton("➕ Добавить пользователя", callback_data="user:add")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="admin:back")])
    return InlineKeyboardMarkup(buttons)

def kb_user_manage(telegram_id, current_role):
    buttons = []
    if current_role != ROLE_SUBADMIN:
        buttons.append([InlineKeyboardButton("⬆️ Сделать Суб-Админом", callback_data=f"user:setrole:{telegram_id}:{ROLE_SUBADMIN}")])
    if current_role != ROLE_EMPLOYEE:
        buttons.append([InlineKeyboardButton("⬇️ Сделать Сотрудником", callback_data=f"user:setrole:{telegram_id}:{ROLE_EMPLOYEE}")])
    buttons.append([InlineKeyboardButton("🗑 Удалить из бота", callback_data=f"user:remove:{telegram_id}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="admin:users")])
    return InlineKeyboardMarkup(buttons)

def kb_projects_menu():
    projects = list_projects()
    buttons = [[InlineKeyboardButton(f"📁 {p['name']}", callback_data=f"proj:edit:{p['id']}")] for p in projects]
    buttons.append([InlineKeyboardButton("➕ Добавить проект", callback_data="proj:add")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="admin:back")])
    return InlineKeyboardMarkup(buttons)

def kb_project_edit(project_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Изменить TOV",       callback_data=f"proj:edittov:{project_id}")],
        [InlineKeyboardButton("📝 Форматы и примеры",  callback_data=f"proj:formats:{project_id}")],
        [InlineKeyboardButton("🗑 Удалить проект",     callback_data=f"proj:delete:{project_id}")],
        [InlineKeyboardButton("◀️ Назад",              callback_data="admin:projects")],
    ])

def kb_project_formats(project_id):
    all_formats     = list_formats()
    linked_ids      = {f["id"] for f in get_project_formats(project_id)}
    buttons = []
    for f in all_formats:
        check = "✅" if f["id"] in linked_ids else "☐"
        buttons.append([InlineKeyboardButton(f"{check} {f['emoji']} {f['name']}", callback_data=f"proj:togglefmt:{project_id}:{f['id']}")])
    buttons.append([InlineKeyboardButton("📄 Примеры по форматам", callback_data=f"proj:exmenu:{project_id}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data=f"proj:edit:{project_id}")])
    return InlineKeyboardMarkup(buttons)

def kb_project_format_examples(project_id):
    formats = get_project_formats(project_id)
    buttons = [[InlineKeyboardButton(f"{f['emoji']} {f['name']}", callback_data=f"proj:exfmt:{project_id}:{f['id']}")] for f in formats]
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data=f"proj:formats:{project_id}")])
    return InlineKeyboardMarkup(buttons)

def kb_format_examples(project_id, format_id):
    examples = get_examples(project_id, format_id)
    buttons  = [[InlineKeyboardButton(f"🗑 {e['filename']}", callback_data=f"proj:delex:{e['id']}:{project_id}:{format_id}")] for e in examples]
    buttons.append([InlineKeyboardButton("➕ Добавить примеры", callback_data=f"proj:addex:{project_id}:{format_id}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data=f"proj:exmenu:{project_id}")])
    return InlineKeyboardMarkup(buttons)

def kb_formats_menu():
    formats = list_formats(active_only=False)
    buttons = [[InlineKeyboardButton(f"{f['emoji']} {f['name']}", callback_data=f"fmt:manage:{f['id']}")] for f in formats]
    buttons.append([InlineKeyboardButton("➕ Добавить формат", callback_data="fmt:add")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="admin:back")])
    return InlineKeyboardMarkup(buttons)

def kb_format_manage(format_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Удалить формат", callback_data=f"fmt:delete:{format_id}")],
        [InlineKeyboardButton("◀️ Назад",          callback_data="admin:formats")],
    ])

def kb_cancel(back_callback="admin:back"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=back_callback)]])

def kb_skip_or_cancel(back_callback="admin:back"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ Пропустить", callback_data="action:skip")],
        [InlineKeyboardButton("❌ Отмена",     callback_data=back_callback)],
    ])
