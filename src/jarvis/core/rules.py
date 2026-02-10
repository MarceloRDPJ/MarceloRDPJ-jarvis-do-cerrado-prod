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
    # RESTART ADGUARD (DNS / INTERNET)
    # =====================================================
    if "adguard" in t or "dns" in t or "internet" in t and "reiniciar" in t:
        return {
            "intent": "system_restart_adguard",
            "action": "request",
            "entity": "container",
            "requires_confirmation": True,
            "confidence": 0.95,
        }

    # =====================================================
    # NETWORK STATUS & SPEED
    # =====================================================
    if "velocidade da internet" in t or "teste de velocidade" in t or "speedtest" in t:
        return {
            "intent": "network_speed",
            "action": "check",
            "entity": "network",
            "confidence": 1.0,
        }

    if "status da internet" in t or "internet ta on" in t or "ping" in t or "conexao" in t:
        return {
            "intent": "network_status",
            "action": "check",
            "entity": "network",
            "confidence": 1.0,
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
    # NETWORK RENAME
    # =====================================================
    # Captura "renomear X por Y" ou "renomear X para Y" ou "renomear X Y"
    # Ex: "Renomear 192.168.1.54 por celular Marcelo"
    rename_match = re.search(r"renomear\s+(\d{1,3}(?:\.\d{1,3}){3})\s+(?:para|por|de)?\s*(.+)", t)
    if rename_match:
        ip = rename_match.group(1)
        name = rename_match.group(2).strip()
        return {
            "intent": "network_rename",
            "action": "rename",
            "entity": "network",
            "params": {
                "target": ip,
                "name": name,
                "text": t
            },
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
    if any(x in t for x in ["listar lembretes", "meus lembretes", "quais lembretes", "agenda", "o que tenho marcado", "lembretes ativos"]):
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

    # Typos comuns (lmebra, lmembra, lembar)
    if re.search(r"\b(l[ea]mbra|lmebra|lembar)\b", t):
        return {
            "intent": "reminder_set",
            "action": "create",
            "entity": "reminder",
            "confidence": 0.7,
        }

    # =====================================================
    # HIDRATAÇÃO (SISTEMA CONSOLIDADO)
    # =====================================================

    # 1. Ativação
    if "ativar hidratação" in t or "ativar hidratacao" in t or "me lembre de beber agua" in t or "me lembre de beber água" in t:
         return {
            "intent": "hydration_activate",
            "action": "activate",
            "entity": "hydration",
            "confidence": 1.0,
        }

    # 2. Status (Acentuação tratada)
    # Prioridade para evitar que caia em system_status
    if any(x in t for x in [
        "status hidratacao", "status hidratação",
        "status da agua", "status da água",
        "quanto bebi", "como ta a agua", "como tá a água", "como está a água",
        "meta de agua", "meta de água"
    ]):
        return {
            "intent": "hydration_status",
            "action": "check",
            "entity": "hydration",
            "confidence": 1.0,
        }

    # 3. Log de Consumo com Valor Específico
    log_match = re.search(r"(?:bebi|tomei|mais)\s*(\d+)\s*(?:ml|l)?", t)
    if log_match:
        return {
            "intent": "hydration_log_explicit",
            "action": "log",
            "entity": "hydration",
            "params": {"amount": int(log_match.group(1))},
            "confidence": 1.0,
        }

    # 4. Log de Consumo Explícito (Sem valor -> Usa copo padrão)
    if any(x in t for x in [
        "bebi agua", "bebi água",
        "tomei agua", "tomei água",
        "mais um copo", "mais uma garrafa",
        "bebi", "ja foi", "já foi", "tomei", "feito", "manda"
    ]):
        return {
            "intent": "hydration_log_explicit",
            "action": "log",
            "entity": "hydration",
            "params": {"amount": None},
            "confidence": 1.0,
        }

    # 5. Log de Consumo Implícito (Depende de contexto/modo)
    # Apenas frases muito curtas e afirmativas
    if t in ["ok", "👍", "beleza", "blz", "joia"]:
        return {
            "intent": "hydration_log_implicit",
            "action": "log",
            "entity": "hydration",
            "params": {"amount": None},
            "confidence": 0.8, # Menor confiança para permitir override de fluxo
        }

    # 6. Controle (Pausa/Cancelamento)
    if re.search(r"(?:pausar|parar|cancelar|silenciar|interromper)\s+(?:hidratação|hidratacao|agua|água)", t):
        return {
            "intent": "hydration_control",
            "action": "control",
            "entity": "hydration",
            "params": {"command": t},
            "confidence": 1.0,
        }

    if re.search(r"(?:retomar|voltar)\s+(?:com\s+)?(?:a\s+)?(?:hidratação|hidratacao|agua|água)", t):
        return {
            "intent": "hydration_control",
            "action": "control",
            "entity": "hydration",
            "params": {"command": t},
            "confidence": 1.0,
        }

    # 7. Edição de Parâmetros
    # Ex: "corrigir meta para 5000", "meu copo agora é 300ml"
    update_match = re.search(r"(?:editar|corrigir|mudar|alterar|definir)\s+(?:meta|copo|total|tamanho|intervalo)(?:.*de\s+)?(?:agua|água|hidratação)?\s*(?:pra|para|é)?\s*(\d+)?", t)
    if update_match:
        val = update_match.group(1)
        return {
            "intent": "hydration_update",
            "action": "update",
            "entity": "hydration",
            "params": {"value": val, "text": t},
            "confidence": 1.0,
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
    # MENUS (ATALHOS)
    # =====================================================
    if "menu rede" in t or "opcoes de rede" in t:
        return {"intent": "menu_network", "action": "show", "entity": "network", "confidence": 1.0}

    if "menu lembrete" in t or "menu tarefas" in t:
        return {"intent": "menu_reminders", "action": "show", "entity": "reminder", "confidence": 1.0}

    if "menu sistema" in t or "opcoes do sistema" in t:
        return {"intent": "menu_system", "action": "show", "entity": "system", "confidence": 1.0}

    # =====================================================
    # NENHUMA REGRA CASOU
    # =====================================================
    return None
