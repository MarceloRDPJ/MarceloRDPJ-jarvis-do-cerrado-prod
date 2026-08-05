# Guia de uso do Jarvis

## Como conversar

Use frases naturais pelo Telegram. Acentos, maiúsculas e vários erros comuns são normalizados. Exemplos equivalentes:

- `speed`, `sped`, `speed teste`, `sped treste`;
- `status`, `status do raspi`, `tempratura do pi`;
- `qual a velocidade da net`, `teste velocdade internet`.

O Jarvis não é um chatbot de conhecimento geral. Se a mensagem não corresponder a uma skill confiável, ele explica o que pode consultar em vez de inventar uma resposta.

## Menus e botões

### Menu principal

- Rede & Segurança
- Agenda & Vida
- Automações
- Sistema & Controle
- Sobre Mim

### Rede & Segurança

- Scan Completo
- Teste Velocidade
- Estatísticas
- Bloquear IP / ajuda
- Renomear Device / ajuda
- Status Internet
- Voltar ao menu principal

### Agenda & Vida

- Ver Lembretes
- Criar Lembrete
- Ativar Hidratação
- Análise 30 Dias
- Bebi Água
- Status Água
- Voltar ao menu principal

### Automações

- Ver Automações
- Configurar Automações
- Voltar ao menu principal

Criar automações novas por texto não é anunciado como disponível quando não existe implementação segura.

### Sistema & Controle

- Diagnóstico
- Ajuda para Reiniciar
- Restart AdGuard
- Ver Logs
- Voltar ao menu principal

Reinício e alterações sensíveis pedem confirmação.

## Funcionalidades e frases

### Raspberry Pi e sistema

- `status`
- `status do raspi`
- `temperatura do pi`
- `logs do sistema`
- `reiniciar sistema`

O status consulta CPU, RAM, disco, temperatura e uptime reais. O Pi não possui sensores ambientais adicionais.

### Internet e rede

- `status da internet`
- `speed`
- `quem ta na rede`
- `estatisticas de rede`
- `renomear 192.168.0.15 para TV Sala`
- `ligar o pc`
- `pc ta ligado?`

O speedtest é uma operação real e pode demorar. O scan depende da visibilidade da rede local.

### AdGuard e segurança

- `bloquear site exemplo.com`
- `reiniciar adguard`
- consultas disponíveis no menu de rede

Bloqueios exigem domínio/IP reconhecido e confirmação. Uma frase muito errada como `bluqear sit` não executa ação.

### Lembretes

- `me lembra de tomar remédio em 20 minutos`
- `me lembra de pagar a conta amanhã às 9h`
- `listar lembretes`
- `lembretes de hoje`
- `lembretes atrasados`
- `apagar lembrete 2`
- `editar lembrete 1`

Os lembretes sobrevivem a reinícios porque usam SQLite no volume persistente.

### Hidratação

- `ativar hidratação`
- `bebi`
- `bebi 500ml`
- `status hidratação`
- `analise de hidratacao`
- `pausar hidratação`
- `retomar hidratação`

### Informações atuais e conversa

Algumas consultas usam RSS ou fontes públicas configuradas. Se a fonte estiver indisponível, a resposta informa a falha. Perguntas gerais sem skill, como `batata combina com banana?`, recebem uma orientação curta; não são enviadas a IA generativa.

## Telegram

- `/start`: abre a apresentação/menu.
- `/help`: mostra ajuda.
- mensagens de texto: passam pelo roteador local.
- botões: enviam callbacks tratados pelo mesmo pipeline.
- acesso: limitado ao `ALLOWED_USER_ID` configurado.

O bot usa long polling, portanto não precisa de webhook público.

## Dashboard local

Na mesma rede, acesse `http://IP_DO_PI:8000/`. O endereço exato depende do IP reservado para o Raspberry Pi. A API de saúde está em `/api/system/health`.

Não exponha a porta 8000 diretamente à internet: este projeto não documenta autenticação própria para o dashboard.

## Quando algo não responder

1. Tente `menu` ou uma frase direta.
2. Verifique se o Telegram e a internet estão acessíveis.
3. No Pi, execute `docker compose ps`.
4. Consulte `docker logs --tail 100 jarvis_cerrado`.
5. Teste o healthcheck local.
