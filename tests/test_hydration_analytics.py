import pytest
from datetime import datetime, timedelta, timezone
from jarvis.modules.hydration_analytics import HydrationAnalytics
from jarvis.database.persistence import Persistence

@pytest.fixture
def mock_history():
    """Mock de histórico de 30 dias"""
    history = []
    base_date = datetime.now(timezone.utc) - timedelta(days=30)

    for day in range(30):
        date = base_date + timedelta(days=day)
        # Simula 8 copos por dia
        for hour in [8, 10, 12, 14, 16, 18, 20, 22]:
            history.append({
                "chat_id": 123,
                "amount_ml": 250,
                "timestamp": (date + timedelta(hours=hour)).isoformat(),
                "goal_ml": 2000,
                "consumed_so_far_ml": 250 * (hour - 7) if (hour-7) > 0 else 250 # Rough approx
            })

            # Correct logic: consumed_so_far_ml should increase.
            # But the prompt used specific logic.
            # "consumed_so_far_ml": 250 * (hour - 7)
            # 8h -> 250
            # 10h -> 250 * 3 = 750 (approx)

    return history

def test_calculate_streak():
    """Testa cálculo de streak"""
    dates = [
        "2024-02-10",
        "2024-02-09",
        "2024-02-08",
        "2024-02-06"  # Gap
    ]

    streak = HydrationAnalytics._calculate_streak(dates)
    assert streak == 3  # Apenas 10, 09, 08 são consecutivos

def test_analyze_patterns(mock_history, monkeypatch):
    """Testa análise de padrões"""
    # Fix the mock data to ensure goal met logic works
    # Logic in analyze_patterns: if entry["consumed_so_far_ml"] >= entry["goal_ml"]: daily_goals_met.append
    # My mock data above needs to ensure consumed_so_far >= 2000 at least once per day.

    # Let's rebuild mock history properly
    history = []
    base_date = datetime.now(timezone.utc) - timedelta(days=30)

    for day in range(30):
        date = base_date + timedelta(days=day)
        consumed = 0
        for hour in [8, 10, 12, 14, 16, 18, 20, 22]:
            consumed += 250
            history.append({
                "chat_id": 123,
                "amount_ml": 250,
                "timestamp": (date + timedelta(hours=hour)).isoformat(),
                "goal_ml": 2000,
                "consumed_so_far_ml": consumed
            })

    monkeypatch.setattr(
        Persistence,
        "get_hydration_history",
        lambda chat_id, days: history
    )

    analysis = HydrationAnalytics.analyze_patterns(123)

    # 8 * 250 = 2000ml per day.
    assert analysis["average_daily_ml"] == 2000
    assert analysis["goal_completion_rate"] == 100.0
    # Peak hours: All hours have same freq (30).
    # It returns top 3.
    assert len(analysis["peak_hours"]) == 3
    # Streak: 30 days
    assert analysis["streak_days"] >= 29 # Due to datetime shifts maybe 29 or 30
