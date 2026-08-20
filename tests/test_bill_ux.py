"""Contas no Telegram: uma mensagem, botões que provam o que fazem, zero pagamento.

A consulta da Equatorial já funcionava; o que faltava era experiência. Estes
testes exercitam o caminho interno de verdade — roteador → executor → job — e os
handlers de callback chamados diretamente, porque não é possível fingir uma
mensagem de entrada pela Bot API.

Nenhum dado real aparece aqui. Payload Pix, referência e PDF são fixtures
inventadas, e os testes verificam estrutura e presença, nunca conteúdo de fatura.
"""

import asyncio
import sys
import types

import pytest

from jarvis.config import Config
from jarvis.core import router
from jarvis.core.executor import Executor

FAKE_PIX = "PIXFAKEPAYLOAD-0000-TESTE"
FAKE_PDF = b"%PDF-1.4 fake boleto de teste"


# =====================================================
# DUBLÊS
# =====================================================
class FakeMessage:
    def __init__(self, message_id):
        self.message_id = message_id


class FakeQuery:
    """Só o que o executor usa de um CallbackQuery: a mensagem para editar."""

    def __init__(self, message_id=77):
        self.message = FakeMessage(message_id)


class FakeBot:
    def __init__(self):
        self.sent = []
        self.edited = []
        self.documents = []
        self.reject_parse_mode = False
        self.document_error = None

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        if parse_mode and self.reject_parse_mode:
            raise RuntimeError("parse_mode recusado pelo Telegram")
        self.sent.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup, "parse_mode": parse_mode}
        )
        return FakeMessage(500 + len(self.sent))

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edited.append(
            {"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup}
        )
        return FakeMessage(message_id)

    async def send_document(self, chat_id, document, filename=None, caption=None):
        if self.document_error:
            raise self.document_error
        self.documents.append(
            {
                "chat_id": chat_id,
                "filename": filename,
                "caption": caption,
                "content": document.read(),
            }
        )
        return FakeMessage(900)


class StubButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class StubMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def install_telegram_stub(monkeypatch):
    """Teclado testável sem depender da biblioteca instalada.

    O ``python-telegram-bot`` deste ambiente está com ``telegram/_bot.py`` vazio,
    então ``import telegram`` levanta ImportError e o executor cai — de propósito —
    para "sem teclado". Provar o cabeamento dos botões exige um stub mínimo; o
    contrário seria testar a corrupção do ambiente, não o produto.
    """
    module = types.ModuleType("telegram")
    module.InlineKeyboardButton = StubButton
    module.InlineKeyboardMarkup = StubMarkup
    monkeypatch.setitem(sys.modules, "telegram", module)


class FakeArtifactStore:
    """Canal de artefato do Pi: id opaco entra, caminho local sai."""

    def __init__(self, artifact_id, path):
        self.artifact_id = artifact_id
        self.path = path
        self.consumed = []

    def resolve(self, artifact_id):
        if artifact_id != self.artifact_id:
            raise KeyError(artifact_id)
        return self.path

    def consume(self, artifact_id):
        self.consumed.append(artifact_id)
        try:
            self.path.unlink()
        except OSError:
            pass


def build_executor(monkeypatch, jobs=None, delays=None, cache=None):
    application = type("App", (), {"bot": FakeBot()})()
    executor = Executor(application)
    monkeypatch.setattr(Config, "ALLOWED_USER_ID", 1, raising=False)
    calls = []

    async def fake_run_poco_job(action, timeout_seconds=70, params=None):
        calls.append({"action": action, "params": dict(params or {})})
        if delays and action in delays:
            await asyncio.sleep(delays[action])
        if action == "read_bill_cache":
            return (cache, None) if cache else (None, "sem cache no Poco.")
        outcome = (jobs or {}).get(action)
        if outcome is None:
            return None, f"acao nao configurada no teste: {action}"
        return outcome

    monkeypatch.setattr(executor, "_run_poco_job", fake_run_poco_job)
    executor.poco_calls = calls
    return executor


def job_calls(executor, action):
    return [call for call in executor.poco_calls if call["action"] == action]


def bill_result(**extra):
    data = {"amount": "R$ 187,90", "reference": "07/2026", "due_date": "12/08/2026"}
    data.update(extra)
    return data


def callback_data(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def wire(code, detail="detalhe tecnico"):
    """Formato exato em que o agente Android entrega um erro tipado."""
    return f"IllegalStateException: {code}: {detail}"


# =====================================================
# C1 — ROTEADOR → EXECUTOR → JOB
# =====================================================
@pytest.mark.asyncio
async def test_typo_in_the_energy_query_still_reaches_the_real_consultation():
    """`conta de lus` é o que o dono digita com pressa; não pode virar conversa."""
    intent = await router.route("conta de lus casa", 1)

    assert intent["intent"] == "equatorial_bills"
    assert intent["params"]["property"] == "casa"


@pytest.mark.asyncio
async def test_misspelled_provider_name_is_understood():
    intent = await router.route("fatura da equatorail", 1)

    assert intent["intent"] == "equatorial_bills"


@pytest.mark.asyncio
async def test_typo_query_keeps_the_named_property():
    intent = await router.route("conta de lus sala comercial", 1)

    assert intent["intent"] == "equatorial_bills"
    assert intent["params"]["property"] == "sala_comercial"


@pytest.mark.asyncio
async def test_conversation_about_a_bill_never_starts_an_automation():
    """Negativo: sem as duas metades (cobrança + energia) não há consulta."""
    intent = await router.route("a conta da padaria ficou cara", 1)

    assert intent["intent"] != "equatorial_bills"


@pytest.mark.asyncio
async def test_consumption_question_is_not_a_bill_consultation():
    """`consumo de energia` é outra skill; roubá-la ligaria o Poco sem pedido."""
    intent = await router.route("consumo de energia", 1)

    assert intent["intent"] != "equatorial_bills"


@pytest.mark.asyncio
async def test_consultation_sends_one_message_and_edits_it_with_the_result(monkeypatch):
    """UMA mensagem por consulta: abre com o aviso e termina no mesmo lugar."""
    executor = build_executor(
        monkeypatch, jobs={"refresh_equatorial_bills": (bill_result(), None)}
    )

    response = await executor.execute(
        {"intent": "equatorial_bills", "action": "read", "params": {"property": "casa"}}, 1
    )

    assert response is None  # o executor já falou; main.py não duplica
    assert len(executor.app.bot.sent) == 1
    assert executor.app.bot.sent[0]["text"] == "⚡ Consultando Equatorial — Casa..."
    assert len(executor.app.bot.edited) == 1
    final = executor.app.bot.edited[0]["text"]
    assert "R$ 187,90" in final
    assert "07/2026" in final


@pytest.mark.asyncio
async def test_result_offers_pix_boleto_refresh_and_back(monkeypatch):
    install_telegram_stub(monkeypatch)
    executor = build_executor(
        monkeypatch, jobs={"refresh_equatorial_bills": (bill_result(), None)}
    )

    await executor._equatorial_bill_flow(1, "casa")

    markup = executor.app.bot.edited[-1]["reply_markup"]
    assert callback_data(markup) == [
        "bill_pix:equatorial:casa",
        "bill_boleto:equatorial:casa",
        "bill_refresh:equatorial:casa",
        "menu_contas",
    ]


@pytest.mark.asyncio
async def test_pix_and_boleto_are_not_loaded_with_the_consultation(monkeypatch):
    """Os botões existem; o artefato só sai quando o dono pedir."""
    executor = build_executor(
        monkeypatch, jobs={"refresh_equatorial_bills": (bill_result(), None)}
    )

    await executor._equatorial_bill_flow(1, "casa")

    assert job_calls(executor, "get_equatorial_pix") == []
    assert job_calls(executor, "get_equatorial_boleto") == []


@pytest.mark.asyncio
async def test_failed_consultation_does_not_offer_payment_buttons(monkeypatch):
    """Sem fatura na tela, oferecer PIX seria prometer o que não existe."""
    install_telegram_stub(monkeypatch)
    executor = build_executor(
        monkeypatch,
        jobs={"refresh_equatorial_bills": (None, wire("EQUATORIAL_BILL_NOT_FOUND"))},
    )

    await executor._equatorial_bill_flow(1, "casa")

    markup = executor.app.bot.edited[-1]["reply_markup"]
    assert callback_data(markup) == ["bill_refresh:equatorial:casa", "menu_contas"]


# =====================================================
# C4 — ATUALIZAR
# =====================================================
@pytest.mark.asyncio
async def test_refresh_button_reuses_the_same_message(monkeypatch):
    executor = build_executor(
        monkeypatch, jobs={"refresh_equatorial_bills": (bill_result(), None)}
    )

    await executor.handle_bill_callback(1, "bill_refresh:equatorial:casa", FakeQuery(77))

    assert executor.app.bot.sent == []  # nada de mensagem nova no chat
    assert [edit["message_id"] for edit in executor.app.bot.edited] == [77, 77]
    assert "R$ 187,90" in executor.app.bot.edited[-1]["text"]


@pytest.mark.asyncio
async def test_refresh_never_mentions_relogin_or_engine_switching(monkeypatch):
    """Detalhe interno de automação não é assunto do dono quando deu certo."""
    executor = build_executor(
        monkeypatch, jobs={"refresh_equatorial_bills": (bill_result(), None)}
    )

    await executor.handle_bill_callback(1, "bill_refresh:equatorial:casa", FakeQuery(77))

    final = executor.app.bot.edited[-1]["text"].lower()
    for leak in ("relogin", "webview", "acessibilidade", "motor", "sessão nova"):
        assert leak not in final


# =====================================================
# C5 — CONCORRÊNCIA (SINGLE-FLIGHT)
# =====================================================
@pytest.mark.asyncio
async def test_two_simultaneous_consultations_create_a_single_poco_job(monkeypatch):
    """O Poco executa um job por vez: dois jobs iguais só dobram a espera."""
    executor = build_executor(
        monkeypatch,
        jobs={"refresh_equatorial_bills": (bill_result(), None)},
        delays={"refresh_equatorial_bills": 0.05},
    )

    await asyncio.gather(
        executor._equatorial_bill_flow(1, "casa"),
        executor._equatorial_bill_flow(1, "casa"),
    )

    assert len(job_calls(executor, "refresh_equatorial_bills")) == 1


@pytest.mark.asyncio
async def test_different_properties_are_not_deduplicated(monkeypatch):
    """Single-flight é por imóvel; senão a kitnet herdaria a leitura da casa."""
    executor = build_executor(
        monkeypatch,
        jobs={"refresh_equatorial_bills": (bill_result(), None)},
        delays={"refresh_equatorial_bills": 0.05},
    )

    await asyncio.gather(
        executor._equatorial_bill_flow(1, "casa"),
        executor._equatorial_bill_flow(1, "kitnet_01"),
    )

    calls = job_calls(executor, "refresh_equatorial_bills")
    assert sorted(call["params"]["property"] for call in calls) == ["casa", "kitnet_01"]


@pytest.mark.asyncio
async def test_second_pix_tap_while_running_does_not_enqueue_another_job(monkeypatch):
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_pix": ({"reference": "07/2026", "pix_payload": FAKE_PIX}, None)},
        delays={"get_equatorial_pix": 0.05},
    )

    first = asyncio.create_task(executor._send_bill_pix(1, "casa"))
    for _ in range(3):
        await asyncio.sleep(0)
    await executor._send_bill_pix(1, "casa")
    await first

    assert len(job_calls(executor, "get_equatorial_pix")) == 1
    assert any("Já estou buscando o Pix" in msg["text"] for msg in executor.app.bot.sent)


@pytest.mark.asyncio
async def test_second_boleto_tap_while_running_does_not_enqueue_another_job(monkeypatch, tmp_path):
    from jarvis.api import app as api_app

    pdf = tmp_path / "artefato.pdf"
    pdf.write_bytes(FAKE_PDF)
    store = FakeArtifactStore("art-1", pdf)
    monkeypatch.setattr(api_app, "get_artifact_store", lambda: store)
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_boleto": ({"reference": "07/2026", "artifact_id": "art-1"}, None)},
        delays={"get_equatorial_boleto": 0.05},
    )

    first = asyncio.create_task(executor._send_bill_boleto(1, "casa"))
    for _ in range(3):
        await asyncio.sleep(0)
    await executor._send_bill_boleto(1, "casa")
    await first

    assert len(job_calls(executor, "get_equatorial_boleto")) == 1
    assert len(executor.app.bot.documents) == 1


# =====================================================
# C2 — PIX
# =====================================================
@pytest.mark.asyncio
async def test_pix_is_delivered_as_copy_and_paste_without_any_payment_link(monkeypatch):
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_pix": ({"reference": "07/2026", "pix_payload": FAKE_PIX}, None)},
    )

    await executor.handle_bill_callback(1, "bill_pix:equatorial:casa", FakeQuery())

    message = executor.app.bot.sent[-1]
    assert "Pix copia e cola — Equatorial Casa — ref. 07/2026" in message["text"]
    assert FAKE_PIX in message["text"]
    assert "<pre>" in message["text"]  # bloco de código: copia com um toque
    assert "http" not in message["text"].lower()


@pytest.mark.asyncio
async def test_pix_falls_back_to_plain_text_when_formatting_is_rejected(monkeypatch):
    """O código precisa chegar mesmo se o Telegram recusar o parse_mode."""
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_pix": ({"reference": "07/2026", "pix_payload": FAKE_PIX}, None)},
    )
    executor.app.bot.reject_parse_mode = True

    await executor._send_bill_pix(1, "casa")

    assert FAKE_PIX in executor.app.bot.sent[-1]["text"]
    assert executor.app.bot.sent[-1]["parse_mode"] is None


@pytest.mark.asyncio
async def test_fresh_artifact_of_the_same_bill_is_reused(monkeypatch):
    executor = build_executor(
        monkeypatch,
        jobs={
            "refresh_equatorial_bills": (bill_result(), None),
            "get_equatorial_pix": ({"reference": "07/2026", "pix_payload": FAKE_PIX}, None),
        },
    )

    await executor._equatorial_bill_flow(1, "casa")
    await executor._send_bill_pix(1, "casa")
    await executor._send_bill_pix(1, "casa")

    assert len(job_calls(executor, "get_equatorial_pix")) == 1
    assert sum(1 for msg in executor.app.bot.sent if FAKE_PIX in msg["text"]) == 2


@pytest.mark.asyncio
async def test_artifact_of_another_bill_is_never_reused(monkeypatch):
    """Reaproveitar o Pix do mês anterior é o erro caro e silencioso desta tela."""
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_pix": ({"reference": "07/2026", "pix_payload": FAKE_PIX}, None)},
    )

    await executor._send_bill_pix(1, "casa")
    # Nova fatura na tela: a referência muda e o artefato guardado perde validade.
    executor._bill_reference[("equatorial", "casa")] = "08/2026"
    await executor._send_bill_pix(1, "casa")

    assert len(job_calls(executor, "get_equatorial_pix")) == 2


@pytest.mark.asyncio
async def test_a_link_is_refused_instead_of_being_forwarded(monkeypatch):
    """Link inicia pagamento. O ROD entrega código, não caminho para pagar."""
    executor = build_executor(
        monkeypatch,
        jobs={
            "get_equatorial_pix": (
                {"reference": "07/2026", "pix_payload": "https://exemplo.invalido/pagar"},
                None,
            )
        },
    )

    await executor._send_bill_pix(1, "casa")

    text = executor.app.bot.sent[-1]["text"]
    assert "não é um Pix copia e cola" in text
    assert "exemplo.invalido" not in text


@pytest.mark.asyncio
async def test_missing_pix_payload_refuses_to_invent_a_code(monkeypatch):
    executor = build_executor(
        monkeypatch, jobs={"get_equatorial_pix": ({"reference": "07/2026"}, None)}
    )

    await executor._send_bill_pix(1, "casa")

    assert "não vou inventar" in executor.app.bot.sent[-1]["text"].lower()


@pytest.mark.asyncio
async def test_pix_payload_never_reaches_the_logs(monkeypatch, caplog):
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_pix": ({"reference": "07/2026", "pix_payload": FAKE_PIX}, None)},
    )

    with caplog.at_level("DEBUG"):
        await executor._send_bill_pix(1, "casa")

    assert FAKE_PIX not in caplog.text


# =====================================================
# C3 — BOLETO
# =====================================================
@pytest.mark.asyncio
async def test_boleto_is_sent_with_a_friendly_name_and_caption(monkeypatch, tmp_path):
    from jarvis.api import app as api_app

    pdf = tmp_path / "artefato.pdf"
    pdf.write_bytes(FAKE_PDF)
    store = FakeArtifactStore("art-1", pdf)
    monkeypatch.setattr(api_app, "get_artifact_store", lambda: store)
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_boleto": ({"reference": "07/2026", "artifact_id": "art-1"}, None)},
    )

    await executor.handle_bill_callback(1, "bill_boleto:equatorial:casa", FakeQuery())

    document = executor.app.bot.documents[-1]
    assert document["filename"] == "Equatorial_Casa_07-2026.pdf"
    assert document["caption"] == "📄 Boleto Equatorial — Casa — referência 07/2026"
    assert document["content"] == FAKE_PDF


@pytest.mark.asyncio
async def test_temporary_boleto_is_gone_after_delivery(monkeypatch, tmp_path):
    from jarvis.api import app as api_app

    pdf = tmp_path / "artefato.pdf"
    pdf.write_bytes(FAKE_PDF)
    store = FakeArtifactStore("art-1", pdf)
    monkeypatch.setattr(api_app, "get_artifact_store", lambda: store)
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_boleto": ({"reference": "07/2026", "artifact_id": "art-1"}, None)},
    )

    await executor._send_bill_boleto(1, "casa")

    assert store.consumed == ["art-1"]
    assert not pdf.exists()


@pytest.mark.asyncio
async def test_a_failed_send_still_removes_the_payment_file(monkeypatch, tmp_path):
    """PDF de pagamento não pode sobrar no disco porque o envio falhou."""
    from jarvis.api import app as api_app

    pdf = tmp_path / "artefato.pdf"
    pdf.write_bytes(FAKE_PDF)
    store = FakeArtifactStore("art-1", pdf)
    monkeypatch.setattr(api_app, "get_artifact_store", lambda: store)
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_boleto": ({"reference": "07/2026", "artifact_id": "art-1"}, None)},
    )
    executor.app.bot.document_error = RuntimeError("upload recusado")

    await executor._send_bill_boleto(1, "casa")

    assert not pdf.exists()
    assert "Nenhum pagamento foi realizado" in executor.app.bot.sent[-1]["text"]


def test_filename_from_the_portal_is_never_used():
    """Nome remoto é entrada não confiável: travessia de diretório e vazamento."""
    hostile = Executor._safe_bill_filename(
        "equatorial", "../../etc/passwd", "07/2026 conta 12345-6"
    )

    assert "/" not in hostile
    assert ".." not in hostile
    assert hostile.endswith(".pdf")


def test_filename_is_built_from_provider_property_and_reference():
    assert (
        Executor._safe_bill_filename("equatorial", "sala_comercial", "07/2026")
        == "Equatorial_Sala-Comercial_07-2026.pdf"
    )


@pytest.mark.asyncio
async def test_missing_artifact_channel_is_explained_without_a_traceback(monkeypatch):
    from jarvis.api import app as api_app

    monkeypatch.setattr(api_app, "get_artifact_store", None)
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_boleto": ({"reference": "07/2026", "artifact_id": "art-1"}, None)},
    )

    await executor._send_bill_boleto(1, "casa")

    text = executor.app.bot.sent[-1]["text"]
    assert "nenhum pagamento foi realizado" in text.lower()
    assert "Traceback" not in text
    assert executor.app.bot.documents == []


# =====================================================
# C6 — ERROS AMIGÁVEIS
# =====================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        wire("EQUATORIAL_AUTH_REQUIRED"),
        wire("EQUATORIAL_HUMAN_CHECK"),
        wire("EQUATORIAL_PROPERTY_NOT_MAPPED"),
        wire("EQUATORIAL_CONTRACT_NOT_FOUND"),
        wire("EQUATORIAL_BILL_NOT_FOUND"),
        wire("EQUATORIAL_PAYMENT_DATA_NOT_FOUND"),
        wire("EQUATORIAL_PORTAL_TIMEOUT"),
        "IllegalStateException: falha desconhecida no agente",
        "java.lang.NullPointerException at EquatorialReader.read(EquatorialReader.java:88)",
    ],
)
async def test_no_typed_code_or_exception_ever_reaches_the_owner(monkeypatch, error):
    executor = build_executor(monkeypatch, jobs={"refresh_equatorial_bills": (None, error)})

    await executor._equatorial_bill_flow(1, "casa")

    text = executor.app.bot.edited[-1]["text"]
    assert "EQUATORIAL_" not in text
    assert "Exception" not in text
    assert ".java:" not in text
    assert text.strip()


@pytest.mark.asyncio
async def test_offline_node_blames_the_phone_not_the_concessionaire(monkeypatch):
    executor = build_executor(
        monkeypatch,
        jobs={"refresh_equatorial_bills": (None, "O Poco está offline ou sem heartbeat recente.")},
    )

    await executor._equatorial_bill_flow(1, "casa")

    assert "Poco está temporariamente indisponível" in executor.app.bot.edited[-1]["text"]


@pytest.mark.asyncio
async def test_disabled_node_is_reported_as_unavailable_not_as_a_portal_problem(monkeypatch):
    executor = build_executor(
        monkeypatch,
        jobs={"refresh_equatorial_bills": (None, "O nó Poco está desativado na configuração.")},
    )

    await executor._equatorial_bill_flow(1, "casa")

    assert "Poco está temporariamente indisponível" in executor.app.bot.edited[-1]["text"]


@pytest.mark.asyncio
async def test_portal_out_of_reach_asks_for_patience(monkeypatch):
    executor = build_executor(
        monkeypatch,
        jobs={"refresh_equatorial_bills": (None, "net::ERR_CONNECTION_TIMED_OUT")},
    )

    await executor._equatorial_bill_flow(1, "casa")

    text = executor.app.bot.edited[-1]["text"]
    assert "A Equatorial não respondeu agora" in text
    assert "net::" not in text


@pytest.mark.asyncio
async def test_human_check_in_every_channel_says_nothing_was_paid(monkeypatch):
    executor = build_executor(
        monkeypatch,
        jobs={
            "refresh_equatorial_bills": (
                None,
                wire("EQUATORIAL_HUMAN_CHECK_ALL_CHANNELS", "webview e chrome"),
            )
        },
    )

    await executor._equatorial_bill_flow(1, "casa")

    text = executor.app.bot.edited[-1]["text"]
    assert "verificação humana em todos os canais" in text
    assert "Nenhum pagamento foi realizado" in text


@pytest.mark.asyncio
async def test_pix_failure_is_humanized_too(monkeypatch):
    """O botão de pagamento não pode ser a porta de saída do erro técnico."""
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_pix": (None, wire("EQUATORIAL_PORTAL_TIMEOUT"))},
    )

    await executor._send_bill_pix(1, "casa")

    text = executor.app.bot.sent[-1]["text"]
    assert "EQUATORIAL_" not in text
    assert "Exception" not in text


# =====================================================
# C7 — MENU
# =====================================================
def test_bills_menu_invents_no_property_before_any_confirmation(monkeypatch):
    install_telegram_stub(monkeypatch)
    executor = build_executor(monkeypatch)

    payload = executor._bills_menu()

    assert callback_data(payload["reply_markup"]) == ["help"]
    assert "não tenho imóvel confirmado" in payload["text"]


@pytest.mark.asyncio
async def test_only_confirmed_properties_become_buttons(monkeypatch):
    install_telegram_stub(monkeypatch)
    executor = build_executor(
        monkeypatch, jobs={"refresh_equatorial_bills": (bill_result(), None)}
    )

    await executor._equatorial_bill_flow(1, "kitnet_01")
    payload = executor._bills_menu()

    assert callback_data(payload["reply_markup"]) == ["bill_menu:kitnet_01", "help"]
    assert "Kitnet 01" in payload["text"] or "Kitnet 01" in str(
        [b.text for row in payload["reply_markup"].inline_keyboard for b in row]
    )


@pytest.mark.asyncio
async def test_a_failed_consultation_does_not_confirm_a_property(monkeypatch):
    """Só leitura concluída prova que a unidade existe no cofre."""
    install_telegram_stub(monkeypatch)
    executor = build_executor(
        monkeypatch,
        jobs={"refresh_equatorial_bills": (None, wire("EQUATORIAL_CONTRACT_NOT_FOUND"))},
    )

    await executor._equatorial_bill_flow(1, "kitnet_02")
    payload = executor._bills_menu()

    assert "bill_menu:kitnet_02" not in callback_data(payload["reply_markup"])


def test_bills_menu_states_the_heartbeat_limitation(monkeypatch):
    """O heartbeat só expõe contagem; o menu diz isso em vez de fingir a lista."""
    install_telegram_stub(monkeypatch)
    from jarvis.api import app as api_app

    monkeypatch.setattr(Config, "POCO_NODE_ENABLED", True, raising=False)
    monkeypatch.setattr(
        api_app,
        "get_poco_service",
        lambda: types.SimpleNamespace(
            status=lambda: {
                "online": True,
                "heartbeat": {
                    "energy_units": 3,
                    "water_units": 2,
                    "equatorial_configured": True,
                    "saneago_configured": True,
                },
            }
        ),
    )
    executor = build_executor(monkeypatch)

    text = executor._bills_menu()["text"]

    assert "3 unidade(s) de energia" in text
    assert "2 de água" in text
    assert "sem os nomes" in text


@pytest.mark.asyncio
async def test_property_menu_shows_only_the_configured_provider(monkeypatch):
    install_telegram_stub(monkeypatch)
    executor = build_executor(
        monkeypatch, jobs={"refresh_equatorial_bills": (bill_result(), None)}
    )

    await executor._equatorial_bill_flow(1, "casa")
    payload = executor._bill_property_menu("casa")

    data = callback_data(payload["reply_markup"])
    assert "bill_refresh:equatorial:casa" in data
    assert "conta de agua casa" not in data  # Saneago nunca foi confirmada aqui
    assert "menu_contas" in data


@pytest.mark.asyncio
async def test_property_menu_hides_energy_when_the_vault_lost_it(monkeypatch):
    install_telegram_stub(monkeypatch)
    from jarvis.api import app as api_app

    executor = build_executor(
        monkeypatch, jobs={"refresh_equatorial_bills": (bill_result(), None)}
    )
    await executor._equatorial_bill_flow(1, "casa")

    monkeypatch.setattr(Config, "POCO_NODE_ENABLED", True, raising=False)
    monkeypatch.setattr(
        api_app,
        "get_poco_service",
        lambda: types.SimpleNamespace(
            status=lambda: {
                "online": True,
                "heartbeat": {"equatorial_configured": False, "saneago_configured": False},
            }
        ),
    )

    payload = executor._bill_property_menu("casa")

    assert callback_data(payload["reply_markup"]) == ["menu_contas"]
    assert "Nenhuma concessionária confirmada" in payload["text"]


@pytest.mark.asyncio
async def test_property_menu_callback_edits_the_open_message(monkeypatch):
    install_telegram_stub(monkeypatch)
    executor = build_executor(monkeypatch)

    await executor.handle_bill_callback(1, "bill_menu:casa", FakeQuery(42))

    assert executor.app.bot.edited[-1]["message_id"] == 42
    assert executor.app.bot.sent == []


# =====================================================
# SEGURANÇA
# =====================================================
@pytest.mark.asyncio
async def test_unauthorized_chat_cannot_use_bill_buttons(monkeypatch):
    executor = build_executor(
        monkeypatch,
        jobs={"get_equatorial_pix": ({"reference": "07/2026", "pix_payload": FAKE_PIX}, None)},
    )

    await executor.handle_bill_callback(999, "bill_pix:equatorial:casa", FakeQuery())

    assert executor.poco_calls == []
    assert executor.app.bot.sent == []


@pytest.mark.asyncio
async def test_an_unexpected_crash_never_shows_the_exception_to_the_owner(monkeypatch):
    """O handler genérico do main responderia com o texto do erro; aqui não sobe."""
    executor = build_executor(monkeypatch)

    async def explode(*args, **kwargs):
        raise RuntimeError("IllegalStateException: EQUATORIAL_BOOM")

    monkeypatch.setattr(executor, "_send_bill_pix", explode)

    await executor.handle_bill_callback(1, "bill_pix:equatorial:casa", FakeQuery())

    text = executor.app.bot.sent[-1]["text"]
    assert "EQUATORIAL_" not in text
    assert "Exception" not in text
    assert "Não consegui consultar a Equatorial agora" in text


@pytest.mark.asyncio
async def test_unknown_bill_callback_is_answered_without_side_effects(monkeypatch):
    executor = build_executor(monkeypatch)

    await executor.handle_bill_callback(1, "bill_pagar:equatorial:casa", FakeQuery())

    assert executor.poco_calls == []
    assert "Não reconheci" in executor.app.bot.sent[-1]["text"]


@pytest.mark.asyncio
async def test_another_provider_is_not_silently_treated_as_equatorial(monkeypatch):
    executor = build_executor(monkeypatch)

    await executor.handle_bill_callback(1, "bill_pix:saneago:casa", FakeQuery())

    assert executor.poco_calls == []
    assert executor.app.bot.documents == []
