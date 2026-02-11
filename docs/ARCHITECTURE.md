# Arquitetura do Sistema - Jarvis do Cerrado 🧠

Esta documentação descreve os princípios técnicos, fluxo de dados e decisões de design.

---

## 🏗️ Visão Geral

O Jarvis do Cerrado é um **chatbot híbrido** que opera em um ambiente local (Raspberry Pi/Docker). Ele combina:
1.  **Determinismo (Local Brain):** Respostas hardcoded para velocidade e confiabilidade offline.
2.  **Inteligência Generativa (Cloud Brain):** LLM (Gemini 2.0 Flash) para contexto e conversação natural.
3.  **Execução Segura (Executor):** Camada isolada que traduz intenções em ações de sistema.

---

## 🔄 Fluxo de Dados (Pipeline)

1.  **Entrada (Input):** O usuário envia uma mensagem no Telegram.
2.  **Roteamento (Router):** O `router.py` analisa a mensagem usando Regex e Fuzzy Matching para identificar a **Intenção (Intent)**.
    *   Ex: "Ligar luz" -> `light_on`
    *   Ex: "Quem é você" -> `identity_who`
3.  **Processamento Cognitivo (Brain):** Se a intenção não for clara ou requerer conversa, o `Brain` entra em ação.
    *   Primeiro tenta o **Local Brain** (base de conhecimento estática).
    *   Se falhar, chama a **API do Gemini** (com System Prompt de identidade).
4.  **Execução (Executor):** O `Executor` recebe a intenção e executa a lógica de negócio (chama APIs, script bash, banco de dados).
5.  **Resposta (Output):** O resultado é formatado e enviado de volta ao Telegram.

---

## 🧩 Componentes Chave

### 1. `Brain` (src/jarvis/core/brain.py)
O cérebro central. Gerencia a decisão entre usar conhecimento local ou nuvem.
*   **System Prompt:** Define a persona (Leal, Goiano, Criado por Marcelo).
*   **Fallback:** Se a API falhar, usa respostas padrão.

### 2. `LocalBrain` (src/jarvis/nlp/local_brain.py)
Um dicionário inteligente com fuzzy matching. Garante que perguntas críticas ("Quem é seu criador") sejam respondidas instantaneamente e corretamente, sem alucinação de LLM.

### 3. `Executor` (src/jarvis/core/executor.py)
A camada de "mãos". É o único módulo autorizado a realizar efeitos colaterais (Side Effects) como:
*   Reiniciar containers.
*   Bloquear IPs no AdGuard.
*   Escrever no banco de dados.

### 4. `Logger` (src/jarvis/core/logger.py)
Sistema de logs rotativo (10MB/arquivo). Garante que falhas sejam rastreáveis sem encher o disco do Raspberry Pi.

---

## 🛡️ Segurança e Robustez

*   **Try/Except Blocks:** Todas as chamadas de rede (Telegram, Gemini) são protegidas.
*   **Timeouts:** Configurados em 20s para evitar travamento da thread principal.
*   **Retry Logic:** O bot tenta reenviar mensagens em caso de falha temporária.
*   **Allowed User ID:** Apenas o ID do Marcelo é autorizado a executar comandos.

---

## 🔮 Futuro

*   Integração com Home Assistant via WebSocket.
*   Suporte a voz (STT/TTS local com Whisper).
*   Dashboard Web local.
