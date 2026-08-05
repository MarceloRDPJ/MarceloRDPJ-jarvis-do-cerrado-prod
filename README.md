# Jarvis do Cerrado

Assistente pessoal e guardião da rede doméstica executado 24/7 em um Raspberry Pi 3B. A interface principal é o Telegram. O atendimento usa regras, NLP local tolerante a erros, contexto curto e skills que consultam dados reais; IA generativa não participa do fluxo de mensagens.

## O que ele faz

- Mostra CPU, RAM, disco, temperatura e uptime reais do Raspberry Pi.
- Verifica internet, ping, velocidade, dispositivos e estatísticas da rede.
- Integra com AdGuard Home para consultas e ações protegidas por confirmação.
- Cria, lista, edita, remove e entrega lembretes persistentes.
- Registra hidratação e apresenta histórico e análise.
- Executa Wake-on-LAN e consulta o estado do computador configurado.
- Monitora rede, energia e eventos, enviando alertas pelo Telegram.
- Oferece menus e botões para rede, agenda, automações e sistema.
- Expõe dashboard e API somente na rede local, na porta `8000`.

## Princípios

- Dado real no lugar de texto inventado.
- Resposta imediata no lugar de timeout de LLM.
- Tolerância maior para consultas; ações perigosas continuam estritas.
- Confirmação humana antes de reinício e bloqueios.
- Persistência local em SQLite e volumes Docker.

## Produção real

- Projeto: `/opt/bot/jarvis-do-cerrado`
- Branch: `main`
- Contêiner: `jarvis_cerrado`
- Compose: `/opt/bot/jarvis-do-cerrado/docker-compose.yml`
- API local: `http://IP_DO_PI:8000/`
- Healthcheck: `http://127.0.0.1:8000/api/system/health`

## Desenvolvimento

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
pytest --no-cov
```

O CI também mede cobertura. A suíte funcional pode passar mesmo quando o limite global de cobertura ainda não for atingido.

## Documentação

- `docs/architecture/technical_architecture.md`: arquitetura física, lógica, rede e nuvem.
- `docs/structure.md`: árvore e responsabilidades do código.
- `docs/user_guide.md`: funcionalidades, frases, menus e botões.
- `docs/deployment.md`: atualização, verificação e recuperação no Pi.
- `docs/specifications/reminders_system.md`: comportamento dos lembretes.
- `AGENTS.md`: regras operacionais para futuros agentes de código.

## Configuração mínima

Copie `.env.example` para `.env` e configure pelo menos:

```env
TELEGRAM_TOKEN=token_do_bot
ALLOWED_USER_ID=id_numerico_autorizado
LOCAL_LLM_ENABLED=false
LOCAL_LLM_BACKEND=disabled
TIMEZONE=America/Sao_Paulo
```

Nunca envie `.env`, token do Telegram, banco de produção ou credenciais ao Git.

## Licença

MIT.
