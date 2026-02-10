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

        # Otimizações para Raspberry Pi
        conn.execute("PRAGMA journal_mode=WAL")  # Menos I/O
        conn.execute("PRAGMA synchronous=NORMAL")  # Performance vs segurança
        conn.execute("PRAGMA cache_size=10000")  # Mais cache
        conn.execute("PRAGMA temp_store=MEMORY")  # Temp em RAM

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
        CREATE TABLE IF NOT EXISTS devices (
            mac TEXT PRIMARY KEY,
            name TEXT,
            updated_at TEXT
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

        # Índices estratégicos
        c.execute("CREATE INDEX IF NOT EXISTS idx_tasks_next_run ON tasks(next_run, status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")

        conn.commit()
        conn.close()

    # ==================================================
    # DEVICES (CUSTOM NAMES)
    # ==================================================
    @staticmethod
    def set_device_name(mac: str, name: str):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO devices (mac, name, updated_at) VALUES (?, ?, ?)",
            (mac, name, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def register_device_seen(mac: str):
        """
        Registra que um dispositivo foi visto, mesmo sem nome.
        Garante que ele exista na tabela 'devices'.
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # Se já existe, não faz nada (preserva o nome se tiver).
        # Se não existe, insere com nome NULL (ou string vazia).
        c.execute(
            "INSERT OR IGNORE INTO devices (mac, name, updated_at) VALUES (?, ?, ?)",
            (mac, "", datetime.now(timezone.utc).isoformat()),
        )
        # Se quisermos atualizar o 'updated_at' sempre:
        if c.rowcount == 0:
             c.execute(
                "UPDATE devices SET updated_at = ? WHERE mac = ?",
                (datetime.now(timezone.utc).isoformat(), mac)
             )
        conn.commit()
        conn.close()

    @staticmethod
    def device_exists(mac: str) -> bool:
        """
        Verifica se um MAC já foi registrado (com ou sem nome).
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM devices WHERE mac=?", (mac,))
        row = c.fetchone()
        conn.close()
        return bool(row)

    @staticmethod
    def update_task_meta(task_id: int, meta: Dict):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE tasks SET meta = ? WHERE id = ?",
            (json.dumps(meta), task_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_device_name(mac: str) -> Optional[str]:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM devices WHERE mac=?", (mac,))
        row = c.fetchone()
        conn.close()
        # Retorna o nome se existir E não for vazio
        return row[0] if row and row[0] else None

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
        try:
            c.execute("SELECT value FROM state WHERE key=?", (key,))
            row = c.fetchone()
            return json.loads(row[0]) if row else default
        except sqlite3.OperationalError:
            return default
        finally:
            conn.close()

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
        meta: Dict = None,
        status: str = "active"
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
                status,
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
    def get_active_tasks(chat_id: int):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT * FROM tasks WHERE chat_id = ? AND status = 'active' ORDER BY next_run ASC",
            (chat_id,),
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

    @staticmethod
    def get_hydration_count_today(chat_id: int) -> int:
        """
        Conta quantas interações de 'confirm' para tarefas do tipo 'hydration' ocorreram hoje.
        """
        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Join tasks and task_interactions
        query = """
            SELECT COUNT(*)
            FROM task_interactions i
            JOIN tasks t ON i.task_id = t.id
            WHERE t.chat_id = ?
              AND t.action = 'hydration'
              AND i.interaction_type = 'confirm'
              AND i.timestamp >= ?
        """
        c.execute(query, (chat_id, start_of_day))
        row = c.fetchone()
        conn.close()
        return row[0] if row else 0

    @staticmethod
    def get_hydration_volume_today(chat_id: int) -> int:
        """
        Soma o volume (ml) de interações 'confirm' para tarefas 'hydration' hoje.
        """
        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Join tasks and task_interactions
        # value é TEXT, precisamos converter
        query = """
            SELECT SUM(CAST(value AS INTEGER))
            FROM task_interactions i
            JOIN tasks t ON i.task_id = t.id
            WHERE t.chat_id = ?
              AND t.action = 'hydration'
              AND i.interaction_type = 'confirm'
              AND i.timestamp >= ?
        """
        c.execute(query, (chat_id, start_of_day))
        row = c.fetchone()
        conn.close()
        # row[0] pode ser None se não houver registros
        return row[0] if row and row[0] else 0

    @staticmethod
    def get_last_cancelled_task_by_action(chat_id: int, action: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM tasks
            WHERE chat_id = ? AND action = ? AND status = 'cancelled'
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id, action),
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_tasks_by_status(chat_id: int, status: str, action: str = None):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        query = "SELECT * FROM tasks WHERE chat_id = ? AND status = ?"
        params = [chat_id, status]

        if action:
            query += " AND action = ?"
            params.append(action)

        c.execute(query, tuple(params))
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

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

    @staticmethod
    def get_last_snapshot() -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            SELECT timestamp, data
            FROM snapshots
            ORDER BY timestamp DESC
            LIMIT 1
            """
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
