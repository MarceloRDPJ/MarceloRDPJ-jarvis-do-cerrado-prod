from jarvis.database.persistence import Persistence

def handle_lock_setup(text, chat_id):
    state = Persistence.get_state(f"flow:{chat_id}")

    if not state:
        Persistence.set_state(f"flow:{chat_id}", {"step": 1})
        return "?? Beleza. Qual nome voc\xea quer dar pra fechadura?"

    step = state["step"]

    if step == 1:
        state["name"] = text
        state["step"] = 2
        Persistence.set_state(f"flow:{chat_id}", state)
        return "Agora manda o *Device ID* dela."

    if step == 2:
        state["device_id"] = text
        state["step"] = 3
        Persistence.set_state(f"flow:{chat_id}", state)
        return "Agora manda a *Local Key*."

    if step == 3:
        state["local_key"] = text
        Persistence.set_state("lock_config", state)
        Persistence.set_state(f"flow:{chat_id}", None)
        return "? Fechadura cadastrada com sucesso."

    return None
