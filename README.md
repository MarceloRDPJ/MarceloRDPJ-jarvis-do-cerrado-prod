# Jarvis do Cerrado 🧠🤖

> *O Guardião Digital da Casa do Marcelo. Autonomia, Eficiência e Segurança Local.*

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Docker](https://img.shields.io/badge/Docker-Container-blue?logo=docker)
![Status](https://img.shields.io/badge/Status-Operacional-green)

O **Jarvis do Cerrado** é um assistente pessoal ultra-otimizado para Raspberry Pi, focado em **segurança de rede (AdGuard)**, **automações domésticas** e **gestão de vida (Agenda/Hidratação)**. Diferente de bots comuns, ele prioriza a execução local (Offline-First) e utiliza IA Generativa (Gemini Flash) apenas como camada de inteligência cognitiva avançada.

---

## 🚀 Funcionalidades Principais

### 1. 🧠 Inteligência Híbrida (Hybrid Brain)
*   **Local Brain (Rápido):** Respostas instantâneas (<10ms) para comandos frequentes e identidade, sem depender de internet.
*   **Cloud Brain (Gemini 2.0 Flash):** Inteligência contextual profunda para conversas naturais, com awareness de que **Marcelo** é o criador.
*   **Fallback Seguro:** Se a internet cair, o bot continua operando comandos locais.

### 2. 🌐 Gestão de Rede & Segurança
*   **Integração AdGuard Home:** Bloqueio de anúncios e rastreadores direto pelo chat.
*   **Scanner de Rede (Deep Scan):** Identifica invasores, novos dispositivos e gera relatórios com fabricantes.
*   **Controle de Acesso:** Bloqueie a internet de dispositivos específicos (ex: TV das crianças) com um comando.

### 3. ⏰ Agenda & Bem-Estar
*   **Lembretes Naturais:** "Me lembra de tirar o lixo amanhã às 18h".
*   **Hidratação Inteligente:** Monitoramento de meta diária com gráficos, streaks e lembretes adaptativos.

### 4. 🖥️ Sistema & Manutenção
*   **Autonomia:** Reinicia containers (AdGuard), monitora temperatura da CPU e uso de disco.
*   **Logs Rotativos:** Sistema de logs robusto para auditoria e debug.

---

## 🛠️ Instalação e Setup

### Pré-requisitos
*   Raspberry Pi (3B+ ou 4) ou qualquer servidor Linux/Docker.
*   Docker & Docker Compose.
*   Conta no Google AI Studio (para API Key do Gemini).
*   Bot Token do Telegram.

### Passo a Passo

1.  **Clone o Repositório:**
    ```bash
    git clone https://github.com/marcelo-rdp/jarvis-cerrado.git
    cd jarvis-cerrado
    ```

2.  **Configure as Variáveis:**
    Crie um arquivo `.env` na raiz:
    ```ini
    TELEGRAM_TOKEN=seu_token_aqui
    ALLOWED_USER_ID=seu_id_telegram
    GEMINI_API_KEY=sua_chave_google_ai
    TZ=America/Sao_Paulo
    ```

3.  **Execute com Docker:**
    ```bash
    docker-compose up -d --build
    ```

4.  **Verifique os Logs:**
    ```bash
    docker logs -f jarvis_cerrado
    ```

---

## 📂 Estrutura do Projeto

A arquitetura segue o padrão modular, separando Cérebro (Brain), Execução (Executor) e Serviços (Services).

```
src/jarvis/
├── core/
│   ├── brain.py       # Orquestrador de Inteligência (Local + Cloud)
│   ├── executor.py    # Executor de Ações (O "Braço" do bot)
│   ├── router.py      # Roteador de Intenções
│   └── logger.py      # Sistema de Logs Centralizado
├── nlp/
│   └── local_brain.py # Base de Conhecimento Estática (Offline)
├── modules/           # Módulos Funcionais (Rede, Sistema, Agenda)
├── services/          # Serviços Background (Cron, Watchdog)
└── main.py            # Ponto de Entrada (ApplicationBuilder)
```

---

## 🧪 Testes e Qualidade

O projeto mantém um padrão rigoroso de qualidade.

### Rodar Testes Unitários
```bash
pytest
```

### Rodar Teste de Estresse (Ultimate)
Simula carga pesada e falhas de rede para garantir robustez.
```bash
python tests/stress_test.py
```

---

## 🤝 Contribuindo

1.  Faça um Fork do projeto.
2.  Crie uma Branch (`git checkout -b feature/nova-funcionalidade`).
3.  Commit suas mudanças (`git commit -m 'Add: Nova funcionalidade'`).
4.  Push para a Branch (`git push origin feature/nova-funcionalidade`).
5.  Abra um Pull Request.

---

**Desenvolvido por Marcelo RDP** | *Powered by Python & Coffee* ☕
