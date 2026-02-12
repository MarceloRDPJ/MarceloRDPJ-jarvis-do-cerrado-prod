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

## 🆕 Wake-on-LAN (Novo!)

Ligue seu PC remotamente via pacote mágico.

### Configuração

1. **Habilite WOL na BIOS/UEFI** do seu PC
2. **Configure o MAC address** no `.env`:
```bash
   PC_MAC=AA:BB:CC:DD:EE:FF
```
3. **Encontre o MAC do seu PC:**
   - Linux: `ip link show`
   - Windows: `ipconfig /all` (MAC = "Endereço Físico")
   - Mac: `ifconfig`

### Comandos

- `Ligar o PC` - Envia pacote WOL
- `Acordar o PC` - Mesmo que acima
- `PC tá ligado?` - Verifica se PC está online

### Como funciona

O Jarvis envia um "magic packet" UDP para o MAC configurado.
O PC precisa:
- ✅ Estar na mesma rede (ou roteador com WOL proxy)
- ✅ WOL habilitado na BIOS
- ✅ Cabo ethernet conectado (Wi-Fi não funciona)

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
