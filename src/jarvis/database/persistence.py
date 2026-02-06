import sqlite3
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "homebot.db")


class Persistence:
    """
    Camada de Persistência do Jarvis.

    RESPONSABILIDADES:
    - Armazenar dados RAW
    - Histórico temporal
    - ZERO interpretação
    """

    # ==================================================
    # INIT
    # ==================================================
    @staticmethod
    def init_db():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            type TEXT,
            source TEXT,
            payload TEXT,
            timestamp TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
        """)

        # Tabela de tarefas atualizada
        c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            text TEXT,
            action TEXT,
            type TEXT, -- 'unique' or 'recurring'
            interval_minutes INTEGER,
            next_run TEXT, -- ISO format datetime
            status TEXT, -- 'active', 'paused', 'cancelled', 'completed'
            meta TEXT, -- JSON with extra fields (meta_ml, cup_ml, etc)
            created_at TEXT
        )
        """)

        # Migração simples: adicionar colunas se não existirem
        # (Em produção real usaria alembic/migrações, aqui fazemos check manual)
        try:
            c.execute("ALTER TABLE tasks ADD COLUMN action TEXT")
        except sqlite3.OperationalError: pass
        try:
            c.execute("ALTER TABLE tasks ADD COLUMN type TEXT")
        except sqlite3.OperationalError: pass
        try:
            c.execute("ALTER TABLE tasks ADD COLUMN next_run TEXT")
        except sqlite3.OperationalError: pass
        try:
            c.execute("ALTER TABLE tasks ADD COLUMN status TEXT")
        except sqlite3.OperationalError: pass
        try:
            c.execute("ALTER TABLE tasks ADD COLUMN meta TEXT")
        except sqlite3.OperationalError: pass
        try:
            c.execute("ALTER TABLE tasks ADD COLUMN created_at TEXT")
        except sqlite3.OperationalError: pass


        c.execute("""
        CREATE TABLE IF NOT EXISTS task_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            interaction_type TEXT, -- 'confirm', 'ignore', 'cancel'
            value TEXT, -- ex: '250' (ml)
            timestamp TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            data TEXT NOT NULL
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS baseline (
            key TEXT PRIMARY KEY,
            data TEXT,
            updated_at TEXT
        )
        """)

        conn.commit()
        conn.close()

    # ==================================================
    # EVENTS
    # ==================================================
    @staticmethod
    def log_event(event):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                (
                    event.id,
                    event.type,
                    event.source,
                    json.dumps(event.payload),
                    event.timestamp,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB Log Error: {e}")

    # ==================================================
    # STATE
    # ==================================================
    @staticmethod
    def set_state(key: str, value: Any):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO state VALUES (?, ?, ?)",
            (key, json.dumps(value), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_state(key: str, default=None):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM state WHERE key=?", (key,))
        row = c.fetchone()
        conn.close()
        return json.loads(row[0]) if row else default

    # ==================================================
    # TASKS (Enhanced)
    # ==================================================
    @staticmethod
    def add_task(
        chat_id: int,
        text: str,
        next_run: datetime,
        action: str = "default",
        task_type: str = "unique",
        interval_minutes: int = 0,
        meta: Dict = None
    ):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO tasks (
                chat_id, text, action, type, interval_minutes,
                next_run, status, meta, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                text,
                action,
                task_type,
                interval_minutes,
                next_run.isoformat(),
                "active",
                json.dumps(meta or {}),
                datetime.now(timezone.utc).isoformat()
            ),
        )
        task_id = c.lastrowid
        conn.commit()
        conn.close()
        return task_id

    @staticmethod
    def update_task_next_run(task_id: int, next_run: datetime):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE tasks SET next_run = ? WHERE id = ?",
            (next_run.isoformat(), task_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def update_task_status(task_id: int, status: str):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE tasks SET status = ? WHERE id = ?",
            (status, task_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_active_tasks_due(now: datetime):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        # Seleciona tarefas ativas que já passaram da hora de execução
        c.execute(
            "SELECT * FROM tasks WHERE status = 'active' AND next_run <= ?",
            (now.isoformat(),),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def get_tasks_by_action(chat_id: int, action: str):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT * FROM tasks WHERE chat_id = ? AND action = ? AND status = 'active'",
            (chat_id, action),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def log_interaction(task_id: int, interaction_type: str, value: str = None):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO task_interactions (task_id, interaction_type, value, timestamp) VALUES (?, ?, ?, ?)",
            (task_id, interaction_type, value, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_task_interactions_today(task_id: int):
        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT value FROM task_interactions WHERE task_id = ? AND timestamp >= ? AND interaction_type = 'confirm'",
            (task_id, start_of_day)
        )
        rows = c.fetchall()
        conn.close()
        return [row[0] for row in rows]

    # ==================================================
    # SNAPSHOTS (RAW)
    # ==================================================
    @staticmethod
    def save_snapshot(snapshot: Dict[str, Any]):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO snapshots (timestamp, data) VALUES (?, ?)",
            (snapshot["timestamp"], json.dumps(snapshot)),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_recent_snapshots(minutes: int, limit: int = 50) -> List[Dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            SELECT timestamp, data
            FROM snapshots
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (since.isoformat(), limit),
        )
        rows = c.fetchall()
        conn.close()

        return [{"timestamp": r[0], **json.loads(r[1])} for r in rows]

    @staticmethod
    def get_snapshot_before(minutes: int) -> Optional[Dict[str, Any]]:
        before = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            SELECT timestamp, data
            FROM snapshots
            WHERE timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (before.isoformat(),),
        )
        row = c.fetchone()
        conn.close()

        return {"timestamp": row[0], **json.loads(row[1])} if row else None

    # ==================================================
    # BASELINE
    # ==================================================
    @staticmethod
    def save_baseline(snapshot: Dict[str, Any]):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT OR REPLACE INTO baseline (key, data, updated_at)
            VALUES ('baseline', ?, ?)
            """,
            (json.dumps(snapshot), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_baseline() -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT data FROM baseline WHERE key='baseline'")
        row = c.fetchone()
        conn.close()

        return json.loads(row[0]) if row else None
