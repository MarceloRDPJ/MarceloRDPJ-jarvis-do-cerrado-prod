import asyncio
import logging
import time
import random
from unittest.mock import AsyncMock, MagicMock

# Ajustar path para importar módulos do src
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'src'))

from jarvis.core.router import route
from jarvis.core.executor import Executor
from jarvis.core.brain import Brain
from jarvis.config import Config

# Configuração de Log para o Teste
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stress_test")

async def simulate_user_message(executor, text, user_id=12345):
    """Simula o fluxo completo de uma mensagem"""
    start_time = time.time()

    # 1. Roteamento
    try:
        intent = await route(text, user_id)
    except Exception as e:
        logger.error(f"Router falhou: {e}")
        return False

    # 2. Execução
    try:
        response = await executor.execute(intent, user_id)
    except Exception as e:
        logger.error(f"Executor falhou: {e}")
        return False

    duration = time.time() - start_time
    return duration

async def stress_test():
    print("🚀 INICIANDO ULTIMATE STRESS TEST")
    print("===================================")

    # Mock Application
    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()
    mock_app.bot.send_chat_action = AsyncMock()

    # Inicializar componentes reais
    executor = Executor(mock_app)

    # Lista de inputs para bombardear o bot
    inputs = [
        "oi", "quem é você", "status do sistema",
        "qual a velocidade da internet", "lembrar de beber agua",
        "quem é marcelo", "ajuda", "logs do sistema",
        "bloquear youtube", "meu ip", "tchau"
    ]

    total_requests = 100  # Aumentar para teste real
    concurrency = 10      # Requests simultâneos

    print(f"📡 Simulando {total_requests} requisições com concorrência {concurrency}...")

    tasks = []
    results = []

    start_global = time.time()

    for i in range(total_requests):
        text = random.choice(inputs)
        # Simula atraso de digitação
        await asyncio.sleep(random.uniform(0.01, 0.05))

        task = asyncio.create_task(simulate_user_message(executor, text))
        tasks.append(task)

        if len(tasks) >= concurrency:
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
            tasks = []

    # Processar restantes
    if tasks:
        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)

    end_global = time.time()
    total_time = end_global - start_global

    # Análise
    successes = [r for r in results if r is not False]
    failures = len(results) - len(successes)
    avg_time = sum(successes) / len(successes) if successes else 0
    max_time = max(successes) if successes else 0

    print("\n📊 RELATÓRIO DE PERFORMANCE")
    print("===================================")
    print(f"✅ Sucessos: {len(successes)}")
    print(f"❌ Falhas:   {failures}")
    print(f"⏱️ Tempo Total: {total_time:.2f}s")
    print(f"⚡ Média por Request: {avg_time:.4f}s")
    print(f"🐢 Pior Request: {max_time:.4f}s")
    print(f"🚀 Throughput: {len(successes)/total_time:.2f} req/s")

    if failures == 0 and avg_time < 0.5:
        print("\n🏆 RESULTADO: PASSED (Google Level Performance)")
    else:
        print("\n⚠️ RESULTADO: NEEDS OPTIMIZATION")

if __name__ == "__main__":
    # Configurar env vars fake se necessario
    os.environ["TELEGRAM_TOKEN"] = "test_token"
    os.environ["ALLOWED_USER_ID"] = "12345"
    asyncio.run(stress_test())
