import sqlite3
import shutil
import glob
import os
from datetime import datetime

# Resolve absolute path to the DB (same logic as persistence.py)
DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "src", "jarvis", "database", "homebot.db"
)
DB_PATH = os.path.normpath(DB_PATH)

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "backups")
BACKUP_DIR = os.path.normpath(BACKUP_DIR)

MAX_BACKUPS = 7


def backup_database():
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Force WAL checkpoint to flush pending writes
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()

    date_str = datetime.now().strftime("%Y-%m-%d")
    backup_path = os.path.join(BACKUP_DIR, f"homebot-{date_str}.db")
    shutil.copy2(DB_PATH, backup_path)
    print(f"Backup created: {backup_path}")

    # Remove old backups, keep only the last MAX_BACKUPS
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "homebot-*.db")))
    while len(backups) > MAX_BACKUPS:
        oldest = backups.pop(0)
        os.remove(oldest)
        print(f"Removed old backup: {oldest}")


if __name__ == "__main__":
    backup_database()
