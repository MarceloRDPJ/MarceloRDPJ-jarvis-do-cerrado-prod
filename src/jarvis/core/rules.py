# -*- coding: utf-8 -*-
"""
Rules Engine — Jarvis do Cerrado

Camada 100% determinística.
NENHUMA IA aqui.
NENHUMA execução aqui.
Apenas decisão explícita de intenção.
"""

from typing import Dict, Optional
import re


def apply_rules(text: str) -> Optional[Dict]:
    """
    Analisa texto normalizado e retorna um intent estruturado
    ou None se nenhuma regra casar.
    """

    if not text or not isinstance(text, str):
        return None

    t = text.lower().strip()

    # =====================================================
    # CONFIRMAÇÃO / CANCELAMENTO DE AÇÃO (PASSO 10)
    # =====================================================
    if t in ("executar", "confirmar", "sim", "autorizar", "pode fazer"):
        return {
            "intent": "action_confirm",
            "action": "confirm",
            "entity": None,
            "confidence": 1.0,
        }

    if t in ("cancelar", "nao", "não", "abortar", "para", "pare"):
        return {
            "intent": "action_cancel",
            "action": "cancel",
            "entity": None,
            "confidence": 1.0,
        }

    # =====================================================
    # GREET
    # =====================================================
    if t in ("oi", "olá", "ola", "e ai", "eai", "fala jarvis"):
        return {
            "intent": "greet",
            "action": None,
            "entity": None,
            "confidence": 1.0,
        }

    # =====================================================
    # HELP
    # =====================================================
    if "ajuda" in t or "help" in t or "o que voce faz" in t:
        return {
            "intent": "help",
            "action": None,
            "entity": None,
            "confidence": 1.0,
        }

    # =====================================================
    # SYSTEM STATUS
    # =====================================================
    if (
        "status da cpu" in t
        or "status do sistema" in t
        or "como esta o sistema" in t
    ):
        return {
            "intent": "system_status",
            "action": "check",
            "entity": "system",
            "confidence": 1.0,
        }

    # =====================================================
    # REBOOT (AÇÃO PERIGOSA → CONFIRMAÇÃO OBRIGATÓRIA)
    # =====================================================
    if re.search(r"\b(reiniciar|reboot|reinicia o sistema)\b", t):
        return {
            "intent": "system_reboot",
            "action": "request",
            "entity": "system",
            "requires_confirmation": True,
            "confidence": 0.95,
        }

    # =====================================================
    # NETWORK SCAN (HUMANO)
    # =====================================================
    if (
        "quem ta na rede" in t
        or "quem esta na rede" in t
        or "scan rede" in t
        or "dispositivos na rede" in t
    ):
        return {
            "intent": "network_scan",
            "action": "scan",
            "entity": "network",
            "confidence": 1.0,
        }

    # =====================================================
    # CONTEXT QUERY (PASSO 6)
    # =====================================================
    if "mudou algo" in t or "teve mudanca" in t:
        return {
            "intent": "context_query",
            "action": "compare",
            "entity": "context",
            "params": {
                "mode": "compare",
                "minutes_ago": 60,
            },
            "confidence": 0.9,
        }

    if "isso e normal" in t or "esta normal" in t:
        return {
            "intent": "context_query",
            "action": "baseline",
            "entity": "context",
            "params": {
                "mode": "baseline",
            },
            "confidence": 0.9,
        }

    # =====================================================
    # LEMBRETES - GERENCIAMENTO (PRIORITÁRIO)
    # =====================================================
    if any(x in t for x in ["listar lembretes", "meus lembretes", "quais lembretes", "agenda", "o que tenho marcado"]):
        return {
            "intent": "reminder_list",
            "action": "list",
            "entity": "reminder",
            "confidence": 1.0,
        }

    delete_match = re.search(r"(?:apagar|remover|esquecer|deletar|cancelar)\s+lembrete\s+(\d+)", t)
    if delete_match:
        return {
            "intent": "reminder_delete",
            "action": "delete",
            "entity": "reminder",
            "params": {"index": int(delete_match.group(1))},
            "confidence": 1.0,
        }

    update_match = re.search(r"(?:editar|mudar|alterar)\s+lembrete\s+(\d+)\s*(.*)", t)
    if update_match:
        index = int(update_match.group(1))
        payload = update_match.group(2).strip()
        # Remove conectivos comuns do início do payload (para, por, as, etc) se necessário
        # Mas vamos deixar o fluxo tratar
        return {
            "intent": "reminder_update",
            "action": "update",
            "entity": "reminder",
            "params": {
                "index": index,
                "modification": payload if payload else None
            },
            "confidence": 1.0,
        }

    # =====================================================
    # LEMBRETES (CRIAÇÃO BÁSICA)
    # =====================================================
    if "lembra" in t or "lembrete" in t:
        return {
            "intent": "reminder_set",
            "action": "create",
            "entity": "reminder",
            "confidence": 0.8,
        }

    # =====================================================
    # BLOQUEIO DE DISPOSITIVO (PREPARADO – PASSO 9)
    # =====================================================
    if re.search(r"\b(bloquear dispositivo|bloqueia esse dispositivo)\b", t):
        return {
            "intent": "network_block_device",
            "action": "request",
            "entity": "network",
            "requires_confirmation": True,
            "confidence": 0.95,
        }

    # =====================================================
    # BLOQUEIO DE SITE (ADGUARD – FUTURO)
    # =====================================================
    if re.search(r"\b(bloquear site|bloqueia site)\b", t):
        return {
            "intent": "network_block_site",
            "action": "request",
            "entity": "network",
            "requires_confirmation": True,
            "confidence": 0.95,
        }

    # =====================================================
    # NENHUMA REGRA CASOU
    # =====================================================
    return None
