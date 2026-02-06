# Processo de Deploy

O Jarvis do Cerrado utiliza uma infraestrutura de deploy imutável baseada em Docker, garantindo que o ambiente de produção seja sempre consistente e previsível.

## Arquitetura de Deploy

O ciclo de vida do deploy segue o fluxo:

```text
GitHub (Main) -> Raspberry Pi (Cron/Script) -> Docker Compose -> Container (Produção)
```

### Componentes

1.  **Dockerfile**: Define a imagem base do ambiente.
    - Base: `python:3.12-slim`
    - Instala dependências de sistema (tcpdump, speedtest, etc.).
    - Instala o pacote `jarvis-do-cerrado` via `pip install -e .`.
    - Define o ponto de entrada: `python -m jarvis.main`.

2.  **Docker Compose**: Orquestra a execução.
    - Mapeia volumes para persistência (`database`, `storage`, `config`).
    - Define reinício automático (`restart: unless-stopped`).
    - Utiliza rede `host` para acesso direto a interfaces de rede (necessário para scanner e WoL).

## Procedimento de Deploy Manual

Em caso de necessidade de intervenção manual no servidor:

1.  Acesse o servidor via SSH (se permitido pela política de rede).
2.  Navegue até o diretório do projeto.
3.  Atualize o código:
    ```bash
    git pull origin main
    ```
4.  Recrie os containers:
    ```bash
    docker compose up -d --build --remove-orphans
    ```

## Automação (Referência)

O sistema foi projetado para suportar auto-update via script agendado (Cron), que executa os passos de pull e rebuild periodicamente, garantindo que o bot esteja sempre na última versão estável da branch principal.
