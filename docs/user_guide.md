# Guia do Usuário - Jarvis do Cerrado

## Instalação

### Requisitos
- Python 3.10 ou superior
- Pip
- Virtualenv (recomendado)

### Passo a Passo

1. **Clone o repositório:**
   ```bash
   git clone <URL_DO_REPOSITORIO>
   cd jarvis-do-cerrado
   ```

2. **Crie um ambiente virtual:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # ou
   .venv\Scripts\activate  # Windows
   ```

3. **Instale as dependências:**
   ```bash
   pip install -e .
   ```

4. **Configuração (.env):**
   Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis (baseado em `src/jarvis/config.py`):

   ```env
   TELEGRAM_TOKEN=seu_token_aqui
   ALLOWED_USER_ID=123456789
   GEMINI_API_KEY=sua_chave_gemini
   # ... outras variáveis conforme necessário
   ```

## Uso

Para iniciar o bot manualmente:

```bash
python -m jarvis.main
```

Interaja com o bot através do Telegram enviando comandos ou texto natural.

## Comandos Comuns

- **Start:** `/start` - Inicia a interação.
- **Status:** "status do sistema" - Verifica saúde do servidor.
- **Rede:** "quem ta na rede" - Lista dispositivos conectados.
- **Ajuda:** "ajuda" - Lista capacidades.
