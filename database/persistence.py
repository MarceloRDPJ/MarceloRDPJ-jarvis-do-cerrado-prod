import sqlite3
import json
import logging
import os
from datetime import datetime, timedelta
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

        c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            text TEXT,
            due_timestamp REAL,
            repeat INTEGER,
            interval_minutes INTEGER
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
            (key, json.dumps(value), datetime.utcnow().isoformat()),
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
    # TASKS
    # ==================================================
    @staticmethod
    def add_task(chat_id, text, due_timestamp, repeat=False, interval_minutes=0):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO tasks (chat_id, text, due_timestamp, repeat, interval_minutes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chat_id, text, due_timestamp, int(repeat), interval_minutes),
        )
        conn.commit()
        conn.close()

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
        since = datetime.utcnow() - timedelta(minutes=minutes)
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
        before = datetime.utcnow() - timedelta(minutes=minutes)
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
            (json.dumps(snapshot), datetime.utcnow().isoformat()),
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
