# DEPRECATED: Use jarvis.database.persistence.Persistence instead
import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"sessions": {}, "locks": {}}

    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_session(chat_id: int) -> dict | None:
    state = load_state()
    return state["sessions"].get(str(chat_id))


def set_session(chat_id: int, session_data: dict) -> None:
    state = load_state()
    state["sessions"][str(chat_id)] = session_data
    save_state(state)


def clear_session(chat_id: int) -> None:
    state = load_state()
    state["sessions"].pop(str(chat_id), None)
    save_state(state)


def save_lock(lock_data: dict) -> None:
    state = load_state()
    state["locks"]["main"] = lock_data
    save_state(state)


def get_lock() -> dict | None:
    state = load_state()
    return state["locks"].get("main")
