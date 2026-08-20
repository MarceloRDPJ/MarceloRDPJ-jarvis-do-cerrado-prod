"""Tela de fatura no Telegram — APRESENTAÇÃO PURA.

Este módulo só monta texto. Não fala com o Poco, não lê banco, não importa
``telegram`` e não decide nada sobre pagamento. Existe separado porque o
contrato de tela do dono é literal e curto, e ele merece um lugar onde possa
ser lido e testado sem subir o executor inteiro:

    ⚡ Equatorial — Casa

    💰 Valor: ...
    🧾 Referência: ...

    [ PIX ] [ BOLETO ] [ ATUALIZAR ] [ VOLTAR ]

Três regras que o formato precisa garantir, e que antes vazavam:

1. **Campo ausente não aparece.** Antes a tela escrevia
   ``Vencimento: indisponível`` — um rótulo com cara de leitura real para um
   dado que a fatura não trouxe. Aqui, sem valor não há linha.
2. **Código de pagamento nunca entra no texto do cartão.** O cartão fica no
   histórico do chat para sempre; o Pix e o código de barras têm validade de
   uma fatura. Escrever o Pix no cartão contornava, de fora, todas as travas
   de frescor do executor: um mês depois o dono rola a conversa, encontra
   ``PIX: ...`` colado num valor e paga a fatura do mês passado sem ter como
   perceber. Código de pagamento sai por botão, ao vivo, ou não sai.
3. **Leitura ao vivo e leitura guardada são visualmente diferentes**, com
   hora na primeira e idade na segunda. "Leitura de agora" sem hora vira
   mentira dez minutos depois, quando a mensagem já é histórico.

Nenhum nome de canal, motor, sessão ou navegador aparece aqui: o dono pediu a
conta, não o mapa da automação.
"""

from typing import Any, Dict, Iterable, Optional

# Ícone e nome público de cada concessionária. É o único vocabulário de
# concessionária que a tela conhece.
PROVIDER_SCREEN: Dict[str, Dict[str, str]] = {
    "equatorial": {"icon": "⚡", "label": "Equatorial", "service": "Energia"},
    "saneago": {"icon": "💧", "label": "Saneago", "service": "Água"},
}

# Texto que algumas leituras trazem no lugar de um valor. Vale como ausência:
# repetir "indisponível" na tela é ruído com aparência de dado.
_ABSENT = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "none",
    "null",
    "indisponivel",
    "indisponível",
    "nao informado",
    "não informado",
}


def provider_icon(provider: str) -> str:
    return PROVIDER_SCREEN.get(str(provider or ""), {}).get("icon", "🧾")


def provider_label(provider: str) -> str:
    screen = PROVIDER_SCREEN.get(str(provider or ""))
    if screen:
        return screen["label"]
    return str(provider or "").replace("_", " ").strip().title() or "Concessionária"


def provider_service(provider: str) -> str:
    """Nome do serviço, para o atalho ("Água", "Energia")."""
    return PROVIDER_SCREEN.get(str(provider or ""), {}).get("service", "Conta")


def field(result: Optional[Dict[str, Any]], *names: str) -> str:
    """Primeiro campo presente de verdade, ou string vazia.

    Ausência é ausência: ``None``, vazio e os placeholders que algumas
    leituras trazem no lugar do dado contam como não ter vindo.
    """
    data = result or {}
    for name in names:
        value = data.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in _ABSENT:
            return text
    return ""


def card_title(provider: str, property_label: str) -> str:
    return f"{provider_icon(provider)} {provider_label(provider)} — {property_label}"


def render_wait(provider: str, property_label: str) -> str:
    """Primeira e única mensagem da consulta.

    A consulta pode levar minutos, e dizer isso aqui seria o lugar natural. Não
    está aqui porque ``tests/test_equatorial_provider_chain.py`` fixa esta linha
    caractere por caractere e aquele arquivo não é meu — o aviso de duração ficou
    no menu do imóvel, que é de onde o dono toca. Está no relatório como pedido
    ao líder.
    """
    return f"{provider_icon(provider)} Consultando {provider_label(provider)} — {property_label}..."


def render_bill_card(
    provider: str,
    property_label: str,
    result: Optional[Dict[str, Any]] = None,
    *,
    read_at: str = "",
) -> str:
    """Cartão da fatura recém-lida, no formato que o dono pediu."""
    amount = field(result, "amount", "valor", "total")
    reference = field(result, "reference", "referencia", "referência")
    due_date = field(result, "due_date", "vencimento")
    consumption = field(result, "consumption", "consumo")

    lines = [card_title(provider, property_label), ""]
    body = []
    if amount:
        body.append(f"💰 Valor: {amount}")
    if reference:
        body.append(f"🧾 Referência: {reference}")
    if due_date:
        body.append(f"📅 Vencimento: {due_date}")
    if consumption:
        body.append(f"📊 Consumo: {consumption}")
    if body:
        lines.extend(body)
    else:
        # Leitura concluída sem os números na tela. Dizer isso é honesto;
        # imprimir rótulos vazios seria fingir que veio dado.
        lines.append("A tela da fatura não trouxe valor nem referência desta vez.")
    lines.append("")
    lines.append(f"🟢 Leitura de agora{f', às {read_at}' if read_at else ''}.")
    return "\n".join(lines)


def format_age(age_seconds: Any) -> str:
    """Idade em palavra de gente. Idade desconhecida não vira número inventado."""
    if not isinstance(age_seconds, (int, float)) or isinstance(age_seconds, bool):
        return "de data desconhecida"
    if age_seconds < 0:
        return "de data desconhecida"
    if age_seconds < 3600:
        return f"de há {int(age_seconds // 60)} min"
    if age_seconds < 86400:
        return f"de há {int(age_seconds // 3600)} h"
    return f"de há {int(age_seconds // 86400)} dia(s)"


def render_stale_block(result: Optional[Dict[str, Any]] = None) -> str:
    """Bloco da leitura guardada, para colar embaixo da falha da consulta.

    Só valor, vencimento e IDADE. Código de barras e Pix existem em parte das
    leituras guardadas e não podem aparecer aqui em nenhuma hipótese: seriam um
    código de pagamento antigo colado a um valor antigo, o que qualquer pessoa
    leria como a cobrança de agora.

    A frase "Última leitura confirmada ... cache do Poco" é contrato de outro
    agente (``tests/test_equatorial_auth.py`` e
    ``tests/test_equatorial_provider_chain.py`` a fixam) e fica. O que muda é o
    que era defeito: ``vencimento indisponível`` — rótulo inventado para um dado
    que a leitura não trouxe — sai, o marcador 🟠 separa esta parte do cartão ao
    vivo, e a última linha diz o que fazer a respeito.
    """
    result = result or {}
    amount = field(result, "amount", "valor")
    due_date = field(result, "due_date", "vencimento")
    head = f"🟠 Última leitura confirmada ({format_age(result.get('cache_age_seconds'))})"
    if amount and due_date:
        head += f": valor {amount}, vencimento {due_date}."
    elif amount:
        head += f": valor {amount}."
    else:
        head += "."
    return (
        f"\n\n{head}\n"
        "Isso é cache do Poco, não a consulta de agora — toque em ATUALIZAR para eu "
        "buscar a fatura de agora."
    )


def render_stale_refusal(provider: str, property_label: str, message: str) -> str:
    """Recusa de pagamento sobre leitura guardada, com a identidade do cartão."""
    return f"{card_title(provider, property_label)}\n\n{message}"


def property_label(property_key: str) -> str:
    return str(property_key or "casa").replace("_", " ").strip().title()


def shortcut_label(provider: str, property_key: str = "") -> str:
    """Rótulo de botão de atalho: ``💧 Água`` ou ``⚡ Kitnet 01``."""
    if property_key:
        return f"{provider_icon(provider)} {property_label(property_key)}"
    return f"{provider_icon(provider)} {provider_service(provider)}"


def limited(keys: Iterable[str], limit: int = 4) -> list:
    """Atalhos em quantidade que ainda é menu, não parede de botões."""
    ordered = sorted({str(key) for key in keys if str(key or "").strip()})
    return ordered[:limit]
