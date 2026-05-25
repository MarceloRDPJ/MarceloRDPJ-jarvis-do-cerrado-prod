import pytest
import sys
import tempfile
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from jarvis.database.persistence import Persistence

@pytest.fixture(autouse=True)
def temp_db():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    Persistence.set_db_path(db_path)
    Persistence.init_db()
    yield
    Persistence.set_db_path(None)
    try:
        os.unlink(db_path)
    except:
        pass
