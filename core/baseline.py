from database.persistence import Persistence
from statistics import mean

class BaselineEngine:
    """
    Calcula padrões normais.
    """

    @staticmethod
    def record(metric: str, value: float):
        history = Persistence.get_state(metric, [])
        history.append(value)

        # Limita histórico
        history = history[-100:]

        Persistence.set_state(metric, history)

    @staticmethod
    def average(metric: str) -> float | None:
        history = Persistence.get_state(metric, [])
        if not history:
            return None
        return mean(history)

    @staticmethod
    def is_anomaly(metric: str, value: float, threshold=1.5) -> bool:
        avg = BaselineEngine.average(metric)
        if not avg:
            return False
        return value > avg * threshold
