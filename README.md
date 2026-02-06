# Jarvis do Cerrado

> **Status:** Produção 24/7 (Raspberry Pi) **Interface:** Telegram Bot **IA:** Determinística + Fallback LLM

Jarvis do Cerrado é um sistema de automação doméstica e monitoramento local projetado para máxima confiabilidade e autonomia.

## 📚 Documentação

- **[Arquitetura Técnica](docs/architecture/technical_architecture.md)**: Visão profunda do sistema, hardware, rede e camadas de software.
- **[Guia do Usuário](docs/user_guide.md)**: Instalação, configuração e uso.
- **[Estrutura do Projeto](docs/structure.md)**: Organização de diretórios e pacotes.
- **[Deploy](docs/deployment.md)**: Processo de deploy automático via Docker.

## 🚀 Quick Start

### Pré-requisitos
- Python 3.10+
- Docker & Docker Compose (para produção)

### Instalação Local

```bash
# Clone o repositório
git clone https://github.com/MarceloRDPJ/MarceloRDPJ-jarvis-do-cerrado-prod.git
cd MarceloRDPJ-jarvis-do-cerrado-prod

# Instale dependências
pip install -e .

# Configure variáveis de ambiente
cp .env.example .env  # (Crie o .env baseado no config.py)

# Execute
python -m jarvis.main
```

### Execução via Docker

```bash
docker compose up -d --build
```

## 🧪 Testes

```bash
python tests/test_bot_logic.py
```

## 📜 Licença

MIT License. Veja `LICENSE` para detalhes.
