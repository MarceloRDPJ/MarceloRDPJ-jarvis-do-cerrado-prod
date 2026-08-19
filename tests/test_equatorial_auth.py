"""Equatorial pela sessão já autenticada do Chrome no Poco.

O agente Android não faz mais login automático. Quando a sessão morre ele devolve
um erro tipado, e o Pi precisa traduzir isso em orientação humana em vez de gastar
tentativas cegas. Os campos opcionais da fatura (código de barras e PIX) só podem
aparecer quando existem de verdade no resultado — inventar linha seria mentir sobre
uma leitura.
"""

import pytest

from jarvis.config import Config
from jarvis.core.executor import Executor


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append(text)


def build_executor(monkeypatch, *, error=None, result=None, cache=None):
    """Executor com o nó Poco substituído por respostas controladas."""
    application = type("App", (), {"bot": FakeBot()})()
    executor = Executor(application)
    monkeypatch.setattr(Config, "ALLOWED_USER_ID", 1, raising=False)

    async def fake_run_poco_job(action, timeout_seconds=70, params=None):
        if action == "read_bill_cache":
            if cache is None:
                return None, "sem cache no Poco."
            return cache, None
        if error is not None:
            return None, error
        return result or {}, None

    monkeypatch.setattr(executor, "_run_poco_job", fake_run_poco_job)
    return executor


@pytest.mark.asyncio
async def test_auth_required_asks_for_manual_login_instead_of_generic_failure(monkeypatch):
    executor = build_executor(
        monkeypatch, error="EQUATORIAL_AUTH_REQUIRED sessao do Chrome expirada"
    )

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "Chrome do Poco" in response
    assert "login novamente na Equatorial" in response
    assert "Não consegui consultar a Equatorial agora" not in response
    assert "EQUATORIAL_AUTH_REQUIRED" not in response


@pytest.mark.asyncio
async def test_auth_required_still_shows_the_labelled_cached_reading(monkeypatch):
    """Leitura antiga continua útil desde que rotulada como cache, nunca como agora."""
    executor = build_executor(
        monkeypatch,
        error="EQUATORIAL_AUTH_REQUIRED sessao expirada",
        cache={"amount": "R$ 210,44", "due_date": "10/08/2026", "cache_age_seconds": 7200},
    )

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "Chrome do Poco" in response
    assert "Última leitura confirmada" in response
    assert "R$ 210,44" in response
    assert "cache do Poco" in response


@pytest.mark.asyncio
async def test_human_check_prefix_returns_the_human_verification_message(monkeypatch):
    executor = build_executor(
        monkeypatch, error="EQUATORIAL_HUMAN_CHECK desafio na tela do portal"
    )

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "verificação humana" in response
    assert "não tenta contornar o bloqueio" in response
    assert "Não consegui consultar a Equatorial agora" not in response


@pytest.mark.asyncio
async def test_keyword_based_human_check_still_works(monkeypatch):
    """O prefixo tipado é adicional; erros antigos por palavra-chave seguem tratados."""
    executor = build_executor(monkeypatch, error="Bloqueio imperva na pagina")

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "verificação humana" in response


@pytest.mark.asyncio
async def test_unknown_error_keeps_the_generic_failure_message(monkeypatch):
    """Negativo: erro comum não pode ser confundido com sessão expirada."""
    executor = build_executor(monkeypatch, error="O Poco não concluiu a tarefa a tempo.")

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "Não consegui consultar a Equatorial agora" in response
    assert "Chrome do Poco" not in response


@pytest.mark.asyncio
async def test_barcode_is_shown_and_absent_pix_is_never_mentioned(monkeypatch):
    executor = build_executor(
        monkeypatch,
        result={
            "amount": "R$ 187,90",
            "reference": "07/2026",
            "due_date": "12/08/2026",
            "barcode": "82640000001-8 79900210442-3",
        },
    )

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "Código de barras: 82640000001-8 79900210442-3" in response
    assert "pix" not in response.lower()


@pytest.mark.asyncio
async def test_pix_is_shown_when_present(monkeypatch):
    executor = build_executor(
        monkeypatch,
        result={
            "amount": "R$ 187,90",
            "reference": "07/2026",
            "due_date": "12/08/2026",
            "pix": "00020126580014BR.GOV.BCB.PIX",
        },
    )

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "PIX: 00020126580014BR.GOV.BCB.PIX" in response
    assert "Código de barras" not in response


@pytest.mark.asyncio
async def test_missing_barcode_and_pix_are_simply_omitted(monkeypatch):
    """Sem os campos no resultado, nada de linha vazia nem de 'indisponível'."""
    executor = build_executor(
        monkeypatch,
        result={"amount": "R$ 187,90", "reference": "07/2026", "due_date": "12/08/2026"},
    )

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "Código de barras" not in response
    assert "pix" not in response.lower()
    assert "R$ 187,90" in response
    assert response.strip().endswith("Vencimento: 12/08/2026")


@pytest.mark.asyncio
async def test_empty_barcode_and_pix_strings_are_treated_as_absent(monkeypatch):
    executor = build_executor(
        monkeypatch,
        result={
            "amount": "R$ 187,90",
            "reference": "07/2026",
            "due_date": "12/08/2026",
            "barcode": "   ",
            "pix": None,
        },
    )

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "Código de barras" not in response
    assert "pix" not in response.lower()
