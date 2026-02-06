class ConversationState:
    """
    Memória de curto prazo por chat (estado de conversa).
    Em breve pode ser persistida no banco.
    """
    _states = {}

    @classmethod
    def get(cls, chat_id):
        return cls._states.get(chat_id)

    @classmethod
    def set(cls, chat_id, state: dict):
        cls._states[chat_id] = state

    @classmethod
    def clear(cls, chat_id):
        cls._states.pop(chat_id, None)
