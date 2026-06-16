import sqlite3
import json
from datetime import datetime

DB_PATH = "bot.db"

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

        CREATE TABLE IF NOT EXISTS project_examples (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id    INTEGER NOT NULL,
            filename      TEXT,
            content       TEXT,
            added_at      TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS formats (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            emoji         TEXT DEFAULT '📝',
            instruction   TEXT NOT NULL,
            active        INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sessions (
            telegram_id   INTEGER PRIMARY KEY,
            project_id    INTEGER,
            format_id     INTEGER,
            history       TEXT DEFAULT '[]',
            updated_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key           TEXT PRIMARY KEY,
            value         TEXT
        );
    """)

    c.execute("SELECT COUNT(*) FROM formats").fetchone()
    if c.execute("SELECT COUNT(*) FROM formats").fetchone()[0] == 0:
        default_formats = [
            ("Пост в Telegram", "📢", "Пишешь пост для Telegram. Длина — до 1500 символов. Абзацы, можно эмодзи. Никаких заголовков с #. Живой язык."),
            ("Пост в Instagram", "📸", "Пишешь пост для Instagram. До 2200 символов. Живой язык, эмодзи уместны. Хэштеги (5–10 штук) в самом конце через пустую строку."),
            ("Статья", "📄", "Пишешь статью. Структура: заголовок H1, подзаголовки H2, развёрнутые абзацы. Длина — от 1000 слов. Экспертный тон."),
            ("Email-рассылка", "📧", "Пишешь письмо для email-рассылки. Тема письма в первой строке после слова ТЕМА:. Длина — 150–300 слов. Чёткий призыв к действию в конце."),
        ]
        c.executemany(
            "INSERT INTO formats (name, emoji, instruction) VALUES (?,?,?)",
            default_formats
        )

    conn.commit()
    conn.close()


# ── Users ──────────────────────────────────────────────────────────────

def get_user(telegram_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def add_user(telegram_id: int, username: str, role: str = "employee", added_by: int = None):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO users (telegram_id, username, role, added_by, added_at) VALUES (?,?,?,?,?)",
        (telegram_id, username, role, added_by, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def update_user_role(telegram_id: int, role: str):
    conn = get_conn()
    conn.execute("UPDATE users SET role=? WHERE telegram_id=?", (role, telegram_id))
    conn.commit()
    conn.close()

def remove_user(telegram_id: int):
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

def create_project(name: str, tov_text: str = "", tov_filename: str = ""):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO projects (name, tov_text, tov_filename, created_at) VALUES (?,?,?,?)",
            (name, tov_text, tov_filename, datetime.now().isoformat())
        )
        conn.commit()
        project_id = conn.execute("SELECT id FROM projects WHERE name=?", (name,)).fetchone()[0]
        conn.close()
        return project_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def get_project(project_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_project_by_name(name: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM projects WHERE name=?", (name,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_project(project_id: int, name: str = None, tov_text: str = None, tov_filename: str = None):
    conn = get_conn()
    proj = dict(conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())
    name = name if name is not None else proj["name"]
    tov_text = tov_text if tov_text is not None else proj["tov_text"]
    tov_filename = tov_filename if tov_filename is not None else proj["tov_filename"]
    conn.execute(
        "UPDATE projects SET name=?, tov_text=?, tov_filename=? WHERE id=?",
        (name, tov_text, tov_filename, project_id)
    )
    conn.commit()
    conn.close()

def delete_project(project_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()
    conn.close()

def list_projects():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_example(project_id: int, filename: str, content: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO project_examples (project_id, filename, content, added_at) VALUES (?,?,?,?)",
        (project_id, filename, content, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_examples(project_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM project_examples WHERE project_id=? ORDER BY added_at",
        (project_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_example(example_id: int):
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

def get_format(format_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM formats WHERE id=?", (format_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_format(name: str, emoji: str, instruction: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO formats (name, emoji, instruction) VALUES (?,?,?)",
        (name, emoji, instruction)
    )
    conn.commit()
    conn.close()

def delete_format(format_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM formats WHERE id=?", (format_id,))
    conn.commit()
    conn.close()


# ── Sessions ───────────────────────────────────────────────────────────

def get_session(telegram_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    if not row:
        return {"telegram_id": telegram_id, "project_id": None, "format_id": None, "history": []}
    d = dict(row)
    d["history"] = json.loads(d["history"])
    return d

def save_session(telegram_id: int, project_id=None, format_id=None, history=None):
    conn = get_conn()
    existing = conn.execute("SELECT telegram_id FROM sessions WHERE telegram_id=?", (telegram_id,)).fetchone()
    if existing:
        fields, vals = [], []
        if project_id is not None: fields.append("project_id=?"); vals.append(project_id)
        if format_id  is not None: fields.append("format_id=?");  vals.append(format_id)
        if history    is not None: fields.append("history=?");    vals.append(json.dumps(history, ensure_ascii=False))
        fields.append("updated_at=?"); vals.append(datetime.now().isoformat())
        vals.append(telegram_id)
        conn.execute(f"UPDATE sessions SET {', '.join(fields)} WHERE telegram_id=?", vals)
    else:
        conn.execute(
            "INSERT INTO sessions (telegram_id, project_id, format_id, history, updated_at) VALUES (?,?,?,?,?)",
            (telegram_id, project_id, format_id, json.dumps(history or [], ensure_ascii=False), datetime.now().isoformat())
        )
    conn.commit()
    conn.close()

def clear_session_history(telegram_id: int):
    save_session(telegram_id, history=[])


# ── Settings ───────────────────────────────────────────────────────────

def get_setting(key: str, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()
