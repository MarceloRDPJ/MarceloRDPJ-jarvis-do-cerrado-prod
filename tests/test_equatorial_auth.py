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


def wire(code: str, detail: str = "detalhe tecnico") -> str:
    """Erro no formato exato em que o agente Android o entrega.

    ``AgentService.describe(Throwable)`` monta ``classe: mensagem`` antes de
    gravar o erro no outbox, e o código tipado nasce dentro de um
    ``IllegalStateException``. Injetar a string crua nos testes escondeu por
    completo o fato de que a tradução no Pi casava pelo início e portanto nunca
    disparava: dos 37 erros registrados em produção, nenhum começava com
    ``EQUATORIAL_``. Todo teste daqui em diante usa o formato do fio.
    """
    return f"IllegalStateException: {code}: {detail}"

@pytest.mark.asyncio
async def test_auth_required_asks_for_manual_login_instead_of_generic_failure(monkeypatch):
    executor = build_executor(
        monkeypatch, error=wire("EQUATORIAL_AUTH_REQUIRED", "sessao do Chrome expirada")
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
async def test_the_barcode_never_reaches_the_message_text(monkeypatch):
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

    # Trava invertida de proposito. Antes isto EXIGIA o codigo dentro do texto,
    # e enquanto exigia existia um formatador que sabia imprimi-lo. Texto fica no
    # historico do Telegram para sempre, e esse caminho contornava de uma vez
    # todas as travas de frescor — TTL, referencia igual e trava de leitura
    # antiga protegem os BOTOES, nao o texto. O codigo sai por botao ou nao sai.
    assert "82640000001" not in response
    assert "digo de barras" not in response
    assert "R$ 187,90" in response


@pytest.mark.asyncio
async def test_the_pix_payload_never_reaches_the_message_text(monkeypatch):
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

    assert "00020126580014" not in response
    assert "pix" not in response.lower()
    assert "R$ 187,90" in response


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
    assert "Vencimento: 12/08/2026" in response


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


@pytest.mark.asyncio
async def test_property_not_mapped_explains_the_learning_step(monkeypatch):
    """O ROD aprende a conta contrato sozinho; o aviso precisa dizer isso.

    Sem essa tradução o dono veria "falhou" e não saberia se o problema é o portal,
    o cadastro do cofre ou a leitura da tela.
    """
    executor = build_executor(
        monkeypatch, error=wire("EQUATORIAL_PROPERTY_NOT_MAPPED", "kitnet_01")
    )

    response = await executor._poco_equatorial_bills({"property": "kitnet_01"})

    assert "conta contrato" in response.lower()
    assert "Kitnet 01" in response
    assert "EQUATORIAL_PROPERTY_NOT_MAPPED" not in response


@pytest.mark.asyncio
async def test_contract_not_found_never_claims_another_property(monkeypatch):
    executor = build_executor(monkeypatch, error=wire("EQUATORIAL_CONTRACT_NOT_FOUND"))

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "não usei dados de outro imóvel" in response.lower()


@pytest.mark.asyncio
async def test_bill_not_found_is_distinct_from_a_broken_reading(monkeypatch):
    """Não ter fatura em aberto é um fato sobre a conta, não uma falha do ROD."""
    executor = build_executor(monkeypatch, error=wire("EQUATORIAL_BILL_NOT_FOUND"))

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "nenhuma fatura" in response.lower()


@pytest.mark.asyncio
async def test_missing_payment_data_refuses_to_invent_a_code(monkeypatch):
    executor = build_executor(monkeypatch, error=wire("EQUATORIAL_PAYMENT_DATA_NOT_FOUND"))

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "não vou inventar" in response.lower()
    assert "código de pagamento" in response.lower()


@pytest.mark.asyncio
async def test_portal_timeout_suggests_retrying(monkeypatch):
    executor = build_executor(monkeypatch, error=wire("EQUATORIAL_PORTAL_TIMEOUT"))

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "não respondeu a tempo" in response.lower()
    assert "repetir a consulta" in response.lower()


@pytest.mark.asyncio
async def test_node_failure_is_not_reported_as_a_concessionaire_failure(monkeypatch):
    """Poco fora do ar não é problema da Equatorial, e o dono não pode ler o oposto.

    Este teste asseverava a mensagem genérica de consulta ("não consegui consultar
    a Equatorial agora") para uma falha que é do aparelho. Estava culpando a
    concessionária por uma queda do nó e, pior, sugeria que o problema estava no
    portal. O caminho genérico continua coberto por
    ``test_unknown_error_keeps_the_generic_failure_message``.
    """
    executor = build_executor(monkeypatch, error="O Poco está offline ou sem heartbeat recente.")

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "Poco está temporariamente indisponível" in response
    assert "heartbeat" not in response.lower()
    assert "Não consegui consultar a Equatorial agora" not in response


@pytest.mark.asyncio
async def test_typed_code_survives_the_exception_wrapper(monkeypatch):
    """Regressão do achado que invalidava toda a tradução de erros.

    Casar pelo início da string parecia razoável e era inútil, porque o agente
    embrulha tudo no nome da exceção antes de enviar. Se alguém trocar a busca
    por ``startswith`` de novo, este teste reprova.
    """
    executor = build_executor(
        monkeypatch, error="IllegalStateException: EQUATORIAL_AUTH_REQUIRED: sessao caiu"
    )

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "Chrome do Poco" in response
    assert "Não consegui consultar a Equatorial agora" not in response


@pytest.mark.asyncio
async def test_portuguese_code_emitted_by_the_agent_is_understood(monkeypatch):
    """O agente ainda emite EQUATORIAL_UC_NAO_ENCONTRADA; nada pode se perder por isso."""
    executor = build_executor(monkeypatch, error=wire("EQUATORIAL_UC_NAO_ENCONTRADA"))

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "não usei dados de outro imóvel" in response.lower()
    assert "Não consegui consultar a Equatorial agora" not in response


@pytest.mark.asyncio
async def test_raw_code_without_wrapper_is_still_understood(monkeypatch):
    """Se o agente parar de embrulhar um dia, a tradução não pode quebrar junto."""
    executor = build_executor(monkeypatch, error="EQUATORIAL_BILL_NOT_FOUND: nada na tela")

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "nenhuma fatura" in response.lower()


@pytest.mark.asyncio
async def test_silent_login_refusal_does_not_blame_the_owner_registration(monkeypatch):
    """O portal recusa a entrada automática sem dizer nada, por decisão antifraude.

    Mandar o dono "conferir o cadastro" aqui o faria caçar um defeito que talvez
    não exista. A mensagem nomeia a causa real e a saída prática.
    """
    executor = build_executor(monkeypatch, error=wire("EQUATORIAL_LOGIN_FAILED"))

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "antifraude" in response.lower()
    assert "nenhum pagamento" in response.lower()
    assert "EQUATORIAL_LOGIN_FAILED" not in response


@pytest.mark.asyncio
async def test_rejected_credentials_are_distinguished_from_a_silent_refusal(monkeypatch):
    """Recusa explícita é a única em que faz sentido apontar o cadastro."""
    executor = build_executor(monkeypatch, error=wire("EQUATORIAL_LOGIN_REJECTED"))

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "unidade consumidora" in response.lower()
    assert "antifraude" not in response.lower()


@pytest.mark.asyncio
async def test_invalid_pix_is_refused_rather_than_delivered(monkeypatch):
    """Entregar um Pix que não valida é pior que não entregar nada.

    O payload pode estar corrompido, e quem paga não tem como saber. A recusa
    precisa ser explícita.
    """
    executor = build_executor(monkeypatch, error=wire("EQUATORIAL_PIX_INVALID"))

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "não vou entregar" in response.lower()
    assert "BR Code" in response


@pytest.mark.asyncio
async def test_ambiguous_pix_never_guesses_which_bill(monkeypatch):
    executor = build_executor(monkeypatch, error=wire("EQUATORIAL_PIX_AMBIGUOUS"))

    response = await executor._poco_equatorial_bills({"property": "casa"})

    assert "outra conta" in response.lower()
