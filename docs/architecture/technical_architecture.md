# Jarvis do Cerrado — Documentação Técnica de Arquitetura (Profunda)

> **Status:** Produção 24/7 (Raspberry Pi) **Deploy:** Auto-deploy via GitHub + Docker + Cron **Interface:** Telegram Bot **IA:** Determinística (sem APIs pagas)

---

## 1. Visão Sistêmica

O **Jarvis do Cerrado** é um sistema de automação doméstica e monitoramento local que opera continuamente em um Raspberry Pi. O projeto foi concebido para máxima **confiabilidade**, **previsibilidade** e **autonomia**, evitando dependências externas e serviços pagos.

O sistema adota um modelo **event-driven** orientado a mensagens, com separação rígida entre:

* interpretação
* decisão
* execução
* persistência

---

## 1.1 Ambiente Físico e Hardware

### Hardware Principal (Servidor Local)

* **Dispositivo:** Raspberry Pi (produção)
* **Arquitetura:** ARM64
* **Sistema Operacional:** Raspberry Pi OS / Debian-based
* **Armazenamento:** microSD / SSD USB (produção recomendada)
* **Operação:** 24/7 (headless)

### Função do Hardware

O Raspberry Pi atua exclusivamente como:

* executor do Jarvis
* host do Docker
* agente de deploy automático

Ele **não é estação de desenvolvimento**. Alterações manuais no servidor devem ser evitadas.

---

## 1.2 Topologia de Rede

### Visão Geral da Rede Doméstica

A arquitetura de rede do **Jarvis do Cerrado** foi desenhada para operar **exclusivamente em ambiente doméstico**, sem exposição pública e com controle total pelo modem/gateway do ISP.

```
Internet
   │
[ Modem / Gateway ISP ]  ← DHCP / NAT / Firewall
   │
   ├── Dispositivos domésticos (Wi‑Fi / LAN)
   │
   └── Raspberry Pi (Jarvis do Cerrado)
```

---

### Modem / Gateway

* **Tipo:** Modem residencial fornecido pelo ISP
* **Função:** Gateway padrão da rede
* **Responsabilidades:**

  * DHCP primário
  * Roteamento NAT
  * Firewall de borda

> ⚠️ Toda a segurança perimetral da rede começa no modem.

---

### Endereçamento IP (Informações Operacionais)

> ⚠️ **Essas informações fazem parte do inventário técnico do projeto e não devem ser alteradas sem documentação.**

* **Gateway (Modem):** `192.168.0.1` *(exemplo / padrão)*
* **Faixa de Rede:** `192.168.0.0/24`

#### Raspberry Pi — Jarvis do Cerrado

* **Hostname:** `jarvis`
* **IP Local:** `192.168.0.XXX` *(IP fixo / reservado no modem)*
* **Tipo de IP:** Estático via DHCP Reservation

Motivos do IP fixo:

* previsibilidade operacional
* monitoramento contínuo
* referência estável em scripts e serviços

> ❗ O IP do Raspberry **não deve mudar**.

---

### Comunicação Externa (Outbound Only)

O Raspberry **não recebe conexões externas**.

Comunicações permitidas:

* **GitHub:** HTTPS / SSH (deploy)
* **Telegram API:** HTTPS (bot)

Comunicações proibidas:

* Port forwarding
* Webhooks públicos
* APIs expostas

Toda comunicação é **iniciada pelo próprio Raspberry**.

---

## 1.3 Segurança de Rede

* ❌ Sem portas abertas
* ❌ Sem SSH exposto à internet
* ✅ Comunicação somente outbound
* ✅ Chaves SSH apenas para GitHub

O Raspberry opera como **cliente**, nunca como servidor público.

---

## 1.4 Dependências de Infraestrutura

Dependências obrigatórias:

* Energia elétrica
* Conectividade com a internet

Dependências não obrigatórias:

* Cloud
* Serviços externos
* APIs pagas

Em caso de queda de internet:

* o bot permanece ativo localmente
* apenas comandos externos são afetados

---

## 1.5 Inventário Técnico Completo (Produção)

> ⚠️ Esta seção documenta **o estado físico real do ambiente**. Alterações devem ser registradas neste documento.

### Raspberry Pi (Servidor Jarvis)

* **Modelo:** Raspberry Pi 4 / 5 *(especificar modelo real quando definido)*
* **Arquitetura:** ARM64
* **CPU:** ARM Cortex (SoC Broadcom)
* **Memória RAM:** 4 GB / 8 GB *(definir conforme hardware real)*
* **Armazenamento Primário:**

  * microSD (boot)
  * SSD USB (dados / produção – recomendado)
* **Sistema Operacional:** Raspberry Pi OS (Debian-based)
* **Modo de Operação:** Headless (sem monitor)
* **Uptime esperado:** 24/7

### Energia

* **Fonte:** Fonte dedicada Raspberry Pi
* **Estabilidade:** Dependente da rede elétrica local
* **Proteção recomendada:**

  * Filtro de linha
  * Nobreak (UPS) para evitar corrupção de dados

### Rede

* **Interface:** Ethernet (preferencial) ou Wi-Fi
* **IP:** Estático (via DHCP Reservation)
* **Gateway:** Modem ISP

---

## 1.6 Limitações Físicas Conhecidas

* CPU limitada (comparada a servidores x86)
* Escrita excessiva em microSD reduz vida útil
* Dependência de energia doméstica

Essas limitações **influenciam decisões de software**.

---

## 1.7 Plano de Falha e Recuperação

### 1️⃣ Falha de Energia

**Cenário:** Queda de energia elétrica

**Impacto:**

* Raspberry desligado abruptamente
* Bot indisponível temporariamente

**Mitigação:**

* Docker configurado com `restart: unless-stopped`
* Sistema sobe automaticamente ao retornar energia

**Recomendação:**

* Uso de nobreak (UPS)

---

### 2️⃣ Falha de Internet

**Cenário:** Internet indisponível

**Impacto:**

* Bot não responde no Telegram
* Deploy automático pausado

**Comportamento esperado:**

* Serviços locais continuam ativos
* Nenhum dado é perdido

**Recuperação:**

* Retorno automático ao restabelecer conexão

---

### 3️⃣ Corrupção de microSD / Storage

**Cenário:** Falha física de armazenamento

**Impacto:**

* Sistema não inicia

**Mitigação:**

* Backup do repositório no GitHub
* Configuração reproduzível via Docker

**Recuperação:**

1. Reinstalar Raspberry Pi OS
2. Clonar repositório
3. Executar `docker compose up -d --build`

---

### 4️⃣ Falha de Software / Bug em Commit

**Cenário:** Commit defeituoso

**Impacto:**

* Bot não sobe corretamente

**Mitigação:**

* Logs centralizados
* Docker isolando falhas

**Recuperação:**

* Reverter commit no GitHub
* Auto-deploy restaura versão anterior

---

## 2. Arquitetura em Camadas

```
[ Telegram ]
      |
      v
[ main.py ]  ← Orquestrador
      |
      v
[ core.brain ]      ← Interpretação
[ core.router ]     ← Roteamento
[ core.executor ]   ← Execução
      |
      v
[ modules/* ]       ← Ações concretas
      |
      v
[ database | storage ]
```

Cada camada tem **responsabilidade única** e **contrato claro**.

---

## 3. main.py — Orquestrador

### Responsabilidades

* Inicializar o bot do Telegram
* Registrar handlers
* Encaminhar mensagens para o Core
* Gerenciar ciclo de vida da aplicação

### Regras

* Não conter lógica de negócio
* Não acessar módulos diretamente
* Não interpretar texto

---

## 4. core/ — Núcleo Cognitivo

### 4.1 core.brain

Função principal:

* Receber texto cru
* Normalizar entrada
* Identificar intenção (`intent`)

Saída:

```python
{
  "intent": "system_status",
  "entities": {"cpu": true},
  "confidence": 0.92
}
```

### 4.2 core.router

Responsável por:

* Decidir fluxo baseado em intent
* Validar contexto
* Escolher ação

Nunca executa nada diretamente.

### 4.3 core.executor

Função:

* Traduz decisão em ação
* Invocar módulo correto
* Controlar exceções

Padrão:

```python
result = module.execute(payload)
```

### 4.4 core.rules

* Regras fixas
* Mapeamento intent → módulo
* Prioridades

### 4.5 core.context

* Estado da conversa
* Multietapas
* Persistência mínima

---

## 5. modules/ — Camada de Execução

Cada módulo:

* Executa **uma responsabilidade**
* Não conhece Telegram
* Não conhece NLP
* Não interpreta texto

### Exemplo: modules/system.py

Funções típicas:

* CPU
* Memória
* Temperatura

Contrato:

```python
def execute(payload: dict) -> dict
```

---

## 6. nlp/ — Processamento de Linguagem Local

Implementa NLP **rule-based**.

Componentes:

* normalizer.py → limpeza de texto
* intent_engine.py → classificação
* time_parser.py → datas/horários

Proibido:

* APIs externas
* LLMs
* Dependências cloud

---

## 7. database/ — Persistência Crítica

### database/persistence.py

Responsável por:

* Lembretes
* Estado do usuário
* Histórico mínimo

Banco:

* SQLite

Regra:

* Dados sobrevivem reinícios

---

## 8. storage/ — Estado Volátil

Armazena:

* Cache
* Estado temporário
* JSONs transitórios

Pode ser apagado sem perda crítica.

---

## 9. services/ — Serviços Autônomos

Exemplos:

* Monitoramento contínuo
* Alertas automáticos

Características:

* Executam em background
* Não respondem diretamente ao usuário

---

## 10. Infraestrutura de Deploy (IMUTÁVEL)

### Pipeline

```
GitHub → Cron → deploy_jarvis.sh → Docker → Bot
```

### Script

* git fetch
* git reset --hard
* docker compose down --remove-orphans
* docker compose up -d --build

Regra absoluta:

> Nunca modificar infra sem justificativa explícita

---

## 11. Filosofia de Design

### Princípios

* Determinismo > Inteligência
* Estado explícito > Mágica
* Logs > Suposições

### Anti-padrões proibidos

* Chatbot genérico
* Lógica espalhada
* Dependência cloud

---

## 12. Identidade e Branding

### Personalidade

* Guardião
* Técnico
* Direto

Exemplo:

> "Sistema estável. Nenhuma anomalia detectada."
