class LockService:
    _registered = False
    _pairing_code = None

    @classmethod
    def is_registered(cls):
        return cls._registered

    @classmethod
    def register(cls, code):
        cls._pairing_code = code
        cls._registered = True

    @classmethod
    def status(cls):
        if not cls._registered:
            return None
        return "online"
