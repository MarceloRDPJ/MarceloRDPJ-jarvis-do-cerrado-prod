# Estrutura do Projeto

O projeto segue um layout `src` padrão para aplicações Python robustas.

## Visão Geral

```text
.
├── Dockerfile              # Definição de imagem para deploy
├── LICENSE                 # Licença do projeto
├── README.md               # Ponto de entrada da documentação
├── docker-compose.yml      # Orquestração de containers
├── docs/                   # Documentação detalhada
├── pyproject.toml          # Metadados do projeto e build
├── requirements.txt        # Dependências (referência)
├── scripts/                # Scripts utilitários (ex: ble_scan.py)
├── setup.py                # Script de instalação legado/compatibilidade
├── src/
│   └── jarvis/             # Pacote principal da aplicação
│       ├── config.py       # Configuração centralizada
│       ├── main.py         # Entry point (Orquestrador)
│       ├── core/           # Núcleo cognitivo e decisório
│       ├── modules/        # Módulos de execução (Hardware/API)
│       ├── services/       # Serviços de background (Guardian, Collector)
│       ├── database/       # Persistência de dados
│       ├── storage/        # Estado volátil
│       └── nlp/            # Processamento de linguagem natural local
└── tests/                  # Testes automatizados
```

## Detalhes dos Pacotes (`src/jarvis`)

### `core/`
O cérebro do sistema.
- **brain.py**: Interface com IA (Gemini) para fallback cognitivo.
- **router.py**: Roteamento de intenções (Regras vs IA).
- **executor.py**: Execução segura de ações.
- **rules.py**: Regras determinísticas de alta prioridade.
- **context.py**: Gerenciamento de contexto de conversação.

### `modules/`
Ações concretas e integrações.
- **system.py**: Monitoramento de hardware (CPU, RAM, Temp).
- **network.py**: Escaneamento de rede e Wake-on-LAN.
- **smarthome.py**: Integração com dispositivos Tuya.
- **reminders.py**: Gestão de agendamentos no Telegram.

### `services/`
Processos que rodam independentemente da interação do usuário.
- **guardian.py**: Monitoramento proativo de anomalias.
- **collector.py**: Coleta periódica de métricas.

### `nlp/`
Processamento local de texto.
- **intent_engine.py**: Motor de regras de intenção.
- **normalizer.py**: Limpeza e normalização de strings.

### `database/`
Persistência de longo prazo.
- **persistence.py**: Abstração do SQLite.
