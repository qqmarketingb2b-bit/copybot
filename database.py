import sqlite3
import json
from datetime import datetime

import os
DB_DIR  = os.environ.get("DB_DIR", "/app/data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "bot.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id   INTEGER PRIMARY KEY,
            username      TEXT,
            role          TEXT DEFAULT 'employee',
            added_by      INTEGER,
            added_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS projects (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT UNIQUE NOT NULL,
            tov_text      TEXT DEFAULT '',
            tov_filename  TEXT DEFAULT '',
            created_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS formats (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            emoji         TEXT DEFAULT '📝',
            instruction   TEXT NOT NULL,
            is_article    INTEGER DEFAULT 0,
            active        INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS project_formats (
            project_id    INTEGER NOT NULL,
            format_id     INTEGER NOT NULL,
            PRIMARY KEY (project_id, format_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (format_id)  REFERENCES formats(id)  ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS project_examples (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id    INTEGER NOT NULL,
            format_id     INTEGER NOT NULL,
            filename      TEXT,
            content       TEXT,
            added_at      TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (format_id)  REFERENCES formats(id)  ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id   INTEGER NOT NULL,
            project_id    INTEGER,
            format_id     INTEGER,
            title         TEXT DEFAULT '',
            status        TEXT DEFAULT 'active',
            history       TEXT DEFAULT '[]',
            created_at    TEXT,
            updated_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS user_state (
            telegram_id     INTEGER PRIMARY KEY,
            active_task_id  INTEGER
        );

        CREATE TABLE IF NOT EXISTS user_projects (
            telegram_id   INTEGER NOT NULL,
            project_id    INTEGER NOT NULL,
            PRIMARY KEY (telegram_id, project_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key           TEXT PRIMARY KEY,
            value         TEXT
        );
    """)

    cols = [r[1] for r in c.execute("PRAGMA table_info(formats)").fetchall()]
    if "is_article" not in cols:
        c.execute("ALTER TABLE formats ADD COLUMN is_article INTEGER DEFAULT 0")

    if c.execute("SELECT COUNT(*) FROM formats").fetchone()[0] == 0:
        default_formats = [
            ("Пост в Telegram", "📢", "Пишешь пост для Telegram. Длина — до 1500 символов. Абзацы, можно эмодзи. Никаких заголовков с #. Живой язык.", 0),
            ("Пост в Instagram", "📸", "Пишешь пост для Instagram. До 2200 символов. Живой язык, эмодзи уместны. Хэштеги (5–10 штук) в самом конце через пустую строку.", 0),
            ("Статья", "📄", "Пишешь статью. Структура: заголовок H1, подзаголовки H2, развёрнутые абзацы. Пиши столько, сколько указано в ТЗ.", 1),
            ("Email-рассылка", "📧", "Пишешь письмо для email-рассылки. Тема письма в первой строке после слова ТЕМА:. Длина — 150–300 слов. Чёткий призыв к действию в конце.", 0),
        ]
        c.executemany("INSERT INTO formats (name, emoji, instruction, is_article) VALUES (?,?,?,?)", default_formats)

    conn.commit()
    conn.close()


# ── Users ──────────────────────────────────────────────────────────────

def get_user(telegram_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_user(telegram_id, username, role="employee", added_by=None):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO users (telegram_id, username, role, added_by, added_at) VALUES (?,?,?,?,?)",
        (telegram_id, username, role, added_by, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def update_user_role(telegram_id, role):
    conn = get_conn()
    conn.execute("UPDATE users SET role=? WHERE telegram_id=?", (role, telegram_id))
    conn.commit()
    conn.close()

def remove_user(telegram_id):
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE telegram_id=?", (telegram_id,))
    conn.commit()
    conn.close()

def list_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Projects ───────────────────────────────────────────────────────────

def create_project(name, tov_text="", tov_filename=""):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO projects (name, tov_text, tov_filename, created_at) VALUES (?,?,?,?)",
            (name, tov_text, tov_filename, datetime.now().isoformat())
        )
        conn.commit()
        pid = conn.execute("SELECT id FROM projects WHERE name=?", (name,)).fetchone()[0]
        conn.close()
        return pid
    except sqlite3.IntegrityError:
        conn.close()
        return None

def get_project(project_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_project_by_name(name):
    conn = get_conn()
    row = conn.execute("SELECT * FROM projects WHERE name=?", (name,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_project(project_id, name=None, tov_text=None, tov_filename=None):
    conn = get_conn()
    proj = dict(conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())
    name = name if name is not None else proj["name"]
    tov_text = tov_text if tov_text is not None else proj["tov_text"]
    tov_filename = tov_filename if tov_filename is not None else proj["tov_filename"]
    conn.execute("UPDATE projects SET name=?, tov_text=?, tov_filename=? WHERE id=?", (name, tov_text, tov_filename, project_id))
    conn.commit()
    conn.close()

def delete_project(project_id):
    conn = get_conn()
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.execute("DELETE FROM user_projects WHERE project_id=?", (project_id,))
    conn.commit()
    conn.close()

def list_projects():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Project ↔ Format links ─────────────────────────────────────────────

def link_project_format(project_id, format_id):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO project_formats (project_id, format_id) VALUES (?,?)", (project_id, format_id))
    conn.commit()
    conn.close()

def unlink_project_format(project_id, format_id):
    conn = get_conn()
    conn.execute("DELETE FROM project_formats WHERE project_id=? AND format_id=?", (project_id, format_id))
    conn.commit()
    conn.close()

def get_project_formats(project_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT f.* FROM formats f
        JOIN project_formats pf ON f.id = pf.format_id
        WHERE pf.project_id=? ORDER BY f.id
    """, (project_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def is_format_linked(project_id, format_id):
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM project_formats WHERE project_id=? AND format_id=?", (project_id, format_id)).fetchone()
    conn.close()
    return row is not None


# ── User ↔ Project access (for employees) ──────────────────────────────

def grant_project_access(telegram_id, project_id):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO user_projects (telegram_id, project_id) VALUES (?,?)", (telegram_id, project_id))
    conn.commit()
    conn.close()

def revoke_project_access(telegram_id, project_id):
    conn = get_conn()
    conn.execute("DELETE FROM user_projects WHERE telegram_id=? AND project_id=?", (telegram_id, project_id))
    conn.commit()
    conn.close()

def has_project_access(telegram_id, project_id):
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM user_projects WHERE telegram_id=? AND project_id=?", (telegram_id, project_id)).fetchone()
    conn.close()
    return row is not None

def get_user_project_ids(telegram_id):
    conn = get_conn()
    rows = conn.execute("SELECT project_id FROM user_projects WHERE telegram_id=?", (telegram_id,)).fetchall()
    conn.close()
    return {r[0] for r in rows}

def list_accessible_projects(telegram_id, role, admin_roles):
    """Admins/Sub-admins see all projects. Employees see only explicitly granted ones."""
    if role in admin_roles:
        return list_projects()
    allowed_ids = get_user_project_ids(telegram_id)
    if not allowed_ids:
        return []
    return [p for p in list_projects() if p["id"] in allowed_ids]


# ── Examples (project + format) ────────────────────────────────────────

def add_example(project_id, format_id, filename, content):
    conn = get_conn()
    conn.execute(
        "INSERT INTO project_examples (project_id, format_id, filename, content, added_at) VALUES (?,?,?,?,?)",
        (project_id, format_id, filename, content, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_examples(project_id, format_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM project_examples WHERE project_id=? AND format_id=? ORDER BY added_at",
        (project_id, format_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_example(example_id):
    conn = get_conn()
    conn.execute("DELETE FROM project_examples WHERE id=?", (example_id,))
    conn.commit()
    conn.close()


# ── Formats ────────────────────────────────────────────────────────────

def list_formats(active_only=True):
    conn = get_conn()
    q = "SELECT * FROM formats WHERE active=1 ORDER BY id" if active_only else "SELECT * FROM formats ORDER BY id"
    rows = conn.execute(q).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_format(format_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM formats WHERE id=?", (format_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_format(name, emoji, instruction, is_article=0):
    conn = get_conn()
    conn.execute("INSERT INTO formats (name, emoji, instruction, is_article) VALUES (?,?,?,?)", (name, emoji, instruction, is_article))
    conn.commit()
    conn.close()

def delete_format(format_id):
    conn = get_conn()
    conn.execute("DELETE FROM formats WHERE id=?", (format_id,))
    conn.commit()
    conn.close()


# ── Tasks (multiple parallel tasks per user) ────────────────────────────

def create_task(telegram_id, project_id=None, format_id=None, title=""):
    conn = get_conn()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO tasks (telegram_id, project_id, format_id, title, status, history, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (telegram_id, project_id, format_id, title, "active", "[]", now, now)
    )
    conn.commit()
    task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return task_id

def get_task(task_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["history"] = json.loads(d["history"])
    return d

def update_task(task_id, project_id=None, format_id=None, title=None, status=None, history=None):
    conn = get_conn()
    fields, vals = [], []
    if project_id is not None: fields.append("project_id=?"); vals.append(project_id)
    if format_id  is not None: fields.append("format_id=?");  vals.append(format_id)
    if title      is not None: fields.append("title=?");      vals.append(title)
    if status     is not None: fields.append("status=?");     vals.append(status)
    if history    is not None: fields.append("history=?");    vals.append(json.dumps(history, ensure_ascii=False))
    fields.append("updated_at=?"); vals.append(datetime.now().isoformat())
    vals.append(task_id)
    conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=?", vals)
    conn.commit()
    conn.close()

def delete_task(task_id):
    conn = get_conn()
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()

def list_user_tasks(telegram_id, status=None):
    conn = get_conn()
    if status:
        rows = conn.execute("SELECT * FROM tasks WHERE telegram_id=? AND status=? ORDER BY updated_at DESC", (telegram_id, status)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tasks WHERE telegram_id=? ORDER BY updated_at DESC", (telegram_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── User active task pointer ─────────────────────────────────────────────

def set_active_task(telegram_id, task_id):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO user_state (telegram_id, active_task_id) VALUES (?,?)", (telegram_id, task_id))
    conn.commit()
    conn.close()

def get_active_task_id(telegram_id):
    conn = get_conn()
    row = conn.execute("SELECT active_task_id FROM user_state WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    return row[0] if row else None

def clear_active_task(telegram_id):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO user_state (telegram_id, active_task_id) VALUES (?, NULL)", (telegram_id,))
    conn.commit()
    conn.close()


# ── Settings ───────────────────────────────────────────────────────────

def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()
