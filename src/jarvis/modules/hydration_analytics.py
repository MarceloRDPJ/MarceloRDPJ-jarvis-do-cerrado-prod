import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from collections import defaultdict
from jarvis.database.persistence import Persistence

logger = logging.getLogger("modules.hydration_analytics")

class HydrationAnalytics:
    """Análise inteligente de padrões de hidratação"""

    @staticmethod
    def analyze_patterns(chat_id: int) -> Dict[str, Any]:
        """
        Analisa padrões de consumo de água.

        Returns:
            {
                "average_daily_ml": float,
                "goal_completion_rate": float,
                "peak_hours": List[int],
                "weak_days": List[str],
                "streak_days": int,
                "suggestions": List[str]
            }
        """
        history = Persistence.get_hydration_history(chat_id, days=30)

        if not history:
            return {"average_daily_ml": 0, "goal_completion_rate": 0, "streak_days": 0, "peak_hours": [], "suggestions": ["Comece a registrar seu consumo de água!"]}

        # Agrupa por dia
        daily_consumption = defaultdict(int)
        hourly_consumption = defaultdict(int)
        daily_goals_met = []

        for entry in history:
            try:
                dt = datetime.fromisoformat(entry["timestamp"])
                date_key = dt.strftime("%Y-%m-%d")
                hour_key = dt.hour

                daily_consumption[date_key] += entry["amount_ml"]
                hourly_consumption[hour_key] += 1

                # Checa se bateu meta naquele dia
                if entry["consumed_so_far_ml"] >= entry["goal_ml"]:
                    if date_key not in daily_goals_met:
                        daily_goals_met.append(date_key)
            except Exception:
                continue

        # Calcula métricas
        days_with_data = len(daily_consumption)
        average_daily = sum(daily_consumption.values()) / days_with_data if days_with_data > 0 else 0
        goal_rate = (len(daily_goals_met) / days_with_data * 100) if days_with_data > 0 else 0

        # Horários de pico (top 3)
        peak_hours = sorted(hourly_consumption.keys(), key=lambda h: hourly_consumption[h], reverse=True)[:3]

        # Dias fracos (dia da semana com menor consumo)
        weekday_consumption = defaultdict(list)
        for date_str, ml in daily_consumption.items():
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            weekday = dt.strftime("%A")
            weekday_consumption[weekday].append(ml)

        weekday_averages = {day: sum(mls)/len(mls) for day, mls in weekday_consumption.items()}
        weak_day = min(weekday_averages.keys(), key=lambda d: weekday_averages[d]) if weekday_averages else None

        # Streak (dias consecutivos batendo meta)
        streak = HydrationAnalytics._calculate_streak(daily_goals_met)

        # Gera sugestões
        suggestions = []

        if goal_rate < 50:
            suggestions.append("📉 Você está batendo menos de 50% das suas metas. Que tal reduzir a meta temporariamente?")
        elif goal_rate > 80:
            suggestions.append("🔥 Mais de 80% de sucesso! Parabéns pela disciplina!")

        if peak_hours:
            suggestions.append(f"⏰ Você bebe mais entre {peak_hours[0]}h-{peak_hours[0]+2}h. Mantenha esse ritmo!")

        if weak_day:
            suggestions.append(f"📅 {weak_day} é seu dia mais fraco. Que tal um lembrete extra?")

        if streak >= 7:
            suggestions.append(f"🔥 {streak} dias consecutivos! Você está imparável!")

        return {
            "average_daily_ml": round(average_daily),
            "goal_completion_rate": round(goal_rate, 1),
            "peak_hours": peak_hours,
            "weak_day": weak_day,
            "streak_days": streak,
            "suggestions": suggestions
        }

    @staticmethod
    def _calculate_streak(dates_met: List[str]) -> int:
        """Calcula quantos dias consecutivos batendo meta"""
        if not dates_met:
            return 0

        # Ordena datas
        try:
            dates_met_sorted = sorted([datetime.strptime(d, "%Y-%m-%d") for d in dates_met], reverse=True)
        except ValueError:
            return 0

        streak = 1
        for i in range(len(dates_met_sorted) - 1):
            diff = (dates_met_sorted[i] - dates_met_sorted[i+1]).days
            if diff == 1:
                streak += 1
            else:
                break

        return streak
