import sqlite3

import pytest

from jarvis.database.persistence import Persistence


class DuplicateCursor:
    def execute(self, sql):
        raise sqlite3.OperationalError("duplicate column name: action")


class BrokenCursor:
    def execute(self, sql):
        raise sqlite3.OperationalError("database is locked")


def test_add_column_ignores_duplicate_column_only():
    Persistence._add_column_if_missing(DuplicateCursor(), "tasks", "action TEXT")


def test_add_column_raises_real_operational_errors():
    with pytest.raises(sqlite3.OperationalError):
        Persistence._add_column_if_missing(BrokenCursor(), "tasks", "action TEXT")
