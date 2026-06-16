import io
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_project, get_examples, get_format, list_projects, list_formats, list_users
from config import ROLE_LABELS, ROLE_ADMIN, ROLE_SUBADMIN, ROLE_EMPLOYEE


# ── Prompt builder ────────────────────────────────────────────────────

def build_system_prompt(project_id: int, format_id: int) -> str:
    proj = get_project(project_id)
    fmt  = get_format(format_id)
    examples = get_examples(project_id)

    tov_block = proj["tov_text"].strip() if proj["tov_text"] else "Пиши в нейтральном профессиональном стиле."

    examples_block = ""
    if examples:
        examples_block = "\n\nПримеры уже одобренных текстов для этого проекта (придерживайся их стиля и подачи):\n"
        for i, ex in enumerate(examples[:5], 1):
            examples_block += f"\n--- Пример {i} ---\n{ex['content'][:1500]}\n"

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

async def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from TXT, basic PDF or DOCX."""
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
            return "[PDF получен, но pypdf не установлен. Установи: pip install pypdf]"
        except Exception as e:
            return f"[Не удалось извлечь текст из PDF: {e}]"

    if fname.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            return "[DOCX получен, но python-docx не установлен. Установи: pip install python-docx]"
        except Exception as e:
            return f"[Не удалось извлечь текст из DOCX: {e}]"

    return f"[Формат файла {filename} не поддерживается. Используй TXT, PDF или DOCX]"


# ── Keyboards ─────────────────────────────────────────────────────────

def kb_main_menu(is_admin: bool):
    buttons = [[InlineKeyboardButton("✍️ Создать текст", callback_data="menu:write")]]
    if is_admin:
        buttons.append([InlineKeyboardButton("⚙️ Панель администратора", callback_data="menu:admin")])
    return InlineKeyboardMarkup(buttons)

def kb_projects():
    projects = list_projects()
    buttons = [[InlineKeyboardButton(p["name"], callback_data=f"project:{p['id']}")] for p in projects]
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)

def kb_formats():
    formats = list_formats()
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
    users = list_users()
    buttons = []
    for u in users:
        label = f"{ROLE_LABELS.get(u['role'], u['role'])} · @{u['username'] or u['telegram_id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"user:manage:{u['telegram_id']}")])
    buttons.append([InlineKeyboardButton("➕ Добавить пользователя", callback_data="user:add")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="admin:back")])
    return InlineKeyboardMarkup(buttons)

def kb_user_manage(telegram_id: int, current_role: str):
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

def kb_project_edit(project_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Изменить TOV",         callback_data=f"proj:edittov:{project_id}")],
        [InlineKeyboardButton("📄 Добавить примеры",     callback_data=f"proj:addex:{project_id}")],
        [InlineKeyboardButton("📋 Показать примеры",     callback_data=f"proj:listex:{project_id}")],
        [InlineKeyboardButton("🗑 Удалить проект",       callback_data=f"proj:delete:{project_id}")],
        [InlineKeyboardButton("◀️ Назад",                callback_data="admin:projects")],
    ])

def kb_formats_menu():
    formats = list_formats(active_only=False)
    buttons = [[InlineKeyboardButton(f"{f['emoji']} {f['name']}", callback_data=f"fmt:manage:{f['id']}")] for f in formats]
    buttons.append([InlineKeyboardButton("➕ Добавить формат", callback_data="fmt:add")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="admin:back")])
    return InlineKeyboardMarkup(buttons)

def kb_format_manage(format_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Удалить формат", callback_data=f"fmt:delete:{format_id}")],
        [InlineKeyboardButton("◀️ Назад",          callback_data="admin:formats")],
    ])

def kb_cancel(back_callback: str = "admin:back"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=back_callback)]])

def kb_skip_or_cancel(back_callback: str = "admin:back"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ Пропустить", callback_data="action:skip")],
        [InlineKeyboardButton("❌ Отмена",     callback_data=back_callback)],
    ])
