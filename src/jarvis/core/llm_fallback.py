import requests
import json
import logging
import os
import signal
import subprocess
import glob
from jarvis.config import Config

logger = logging.getLogger(__name__)

# Caminhos comuns para auto-descoberta
_COMMON_CLI_PATHS = [
    "/opt/bot/llama.cpp/build/bin/llama-cli",
    "/usr/local/bin/llama-cli",
    "/usr/bin/llama-cli",
]
_COMMON_MODEL_DIRS = [
    "/opt/bot/models",
    "/models",
    "/home/pi/models",
    "/home/marcelo/models",
]


def _find_first_file(paths, pattern="*.gguf"):
    for base in paths:
        if os.path.isdir(base):
            matches = sorted(glob.glob(os.path.join(base, pattern)))
            if matches:
                return matches[0]
    return None


def _discover_cli():
    for p in _COMMON_CLI_PATHS:
        if os.path.exists(p):
            logger.info(f"Auto-descoberta: llama-cli em {p}")
            return p
    return None


def _discover_model():
    path = _find_first_file(_COMMON_MODEL_DIRS)
    if path:
        logger.info(f"Auto-descoberta: modelo em {path}")
    return path


JARVIS_SYSTEM_PROMPT = (
    "Você é o Jarvis do Cerrado, assistente doméstico local do Marcelo, "
    "rodando em um Raspberry Pi 3B. "
    "Você ajuda com automação residencial, rede local, Docker, Raspberry Pi, "
    "serviços do servidor e perguntas gerais. "
    "Responda em português do Brasil, de forma direta, natural e segura. "
    "Não invente informações atuais. "
    "Quando a pergunta depende de dados recentes, use pesquisa na internet. "
    "Quando não conseguir confirmar algo, avise honestamente. "
    "Nunca revele tokens, senhas ou chaves. "
    "Nunca execute ações perigosas sem confirmação. "
    "Seja útil e conciso."
)

LOCAL_LLM_TIMEOUT_MESSAGE = "A LLM local não respondeu dentro do limite. Tente uma pergunta menor."


class LLMFallbackEngine:
    def __init__(self):
        self.backend = Config.LOCAL_LLM_BACKEND if Config.LOCAL_LLM_ENABLED else "disabled"
        self.url = Config.LOCAL_LLM_URL
        self.model = Config.LOCAL_LLM_MODEL
        self.cli_path = Config.LOCAL_LLM_CLI_PATH or _discover_cli()
        self.model_path = Config.LOCAL_LLM_MODEL_PATH or _discover_model()
        self.context_tokens = Config.LOCAL_LLM_CONTEXT_TOKENS
        self.threads = Config.LOCAL_LLM_THREADS
        self.timeout = Config.LOCAL_LLM_TIMEOUT_SECONDS
        self.max_tokens = Config.LOCAL_LLM_MAX_TOKENS
        self.temperature = Config.LOCAL_LLM_TEMPERATURE

        if not self.cli_path or not self.model_path:
            logger.warning(f"LLM local não configurado (cli={self.cli_path}, model={self.model_path}). Use LOCAL_LLM_CLI_PATH e LOCAL_LLM_MODEL_PATH no .env")

    def is_available(self) -> bool:
        """Checa se o backend local está respondendo."""
        if self.backend == "disabled":
            return False
        if self.backend == "llamacpp_cli":
            return bool(
                self.cli_path
                and self.model_path
                and os.path.exists(self.cli_path)
                and os.path.exists(self.model_path)
            )
        try:
            base_url = self.url.rsplit("/", 1)[0]
            requests.get(base_url, timeout=1)
            return True
        except Exception:
            return False

    def get_status_message(self) -> str:
        status = "disponível" if self.is_available() else "indisponível"
        backend = self.backend
        model = os.path.basename(self.model_path) if self.model_path else "não configurado"
        cli = self.cli_path or "não configurado"
        return (
            f"LLM local: {status}\n"
            f"Backend: {backend}\n"
            f"Modelo: {model}\n"
            f"CLI: {cli}\n"
            f"Timeout: {self.timeout}s\n"
            f"Tokens: {self.max_tokens}\n"
            f"Threads: {self.threads}\n"
            f"Contexto: {self.context_tokens}"
        )

    def generate_chat_response(self, text: str) -> str:
        """Gera resposta de chat livre (não-JSON)"""
        if self.backend == "disabled":
            return None

        prompt = (
            f"System: {JARVIS_SYSTEM_PROMPT}\n"
            f"User: {text}\nAssistant:"
        )

        return self._generate_prompt(prompt, temperature=self.temperature)

    def generate_response_with_context(self, question: str, context: str) -> str:
        """Usa o LLM local para formular resposta com dados coletados localmente."""
        if self.backend == "disabled" or not context:
            return None

        prompt = (
            f"System: {JARVIS_SYSTEM_PROMPT}\n"
            "Você recebeu dados coletados por ferramentas locais gratuitas. "
            "Responda apenas com base no contexto. Se o contexto for insuficiente, diga isso.\n"
            f"Contexto:\n{context}\n\n"
            f"User: {question}\nAssistant:"
        )
        return self._generate_prompt(prompt, temperature=self.temperature)

    def _generate_prompt(self, prompt: str, temperature: float) -> str:
        if self.backend == "disabled":
            return None

        if self.backend == "llamacpp_cli":
            return self._generate_with_cli(prompt, temperature=temperature)

        payload = self._build_payload(prompt, temperature=temperature)

        try:
            response = requests.post(self.url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            return self._extract_text(result).strip() or None
        except requests.exceptions.ConnectionError:
            logger.debug("LLM local offline.")
            return None
        except Exception as e:
            logger.error(f"Erro no LLMFallbackEngine (Chat): {e}")
            return None

    def interpret(self, text: str, context: dict = None) -> dict:
        """Tenta extrair intenção em JSON (mantido para compatibilidade futura)"""
        prompt = f"""
        Responda APENAS com JSON válido.
        Texto: "{text}"
        Contexto: {json.dumps(context) if context else 'nenhum'}
        Formato: {{"intent": "<valor>", "entities": {{}}}}
        """

        if self.backend == "disabled":
            return None

        if self.backend == "llamacpp_cli":
            generated_text = self._generate_with_cli(prompt, temperature=0.1)
            if not generated_text:
                return None
            try:
                generated_text = generated_text.replace("```json", "").replace("```", "").strip()
                return json.loads(generated_text)
            except json.JSONDecodeError:
                logger.warning(f"Falha ao decodificar JSON do LLM: {generated_text}")
                return None

        payload = self._build_payload(prompt, temperature=0.1)

        try:
            response = requests.post(self.url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()

            generated_text = self._extract_text(result)

            # Clean up potential markdown code blocks
            generated_text = generated_text.replace("```json", "").replace("```", "").strip()

            return json.loads(generated_text)

        except requests.exceptions.ConnectionError:
            logger.debug("LLM local não está acessível (ConnectionError) - Ignorando fallback local.")
            return None
        except json.JSONDecodeError:
            logger.warning(f"Falha ao decodificar JSON do LLM: {generated_text}")
            return None
        except Exception as e:
            logger.error(f"Erro no LLMFallbackEngine (Interpret): {e}")
            return None

    def _build_payload(self, prompt: str, temperature: float) -> dict:
        if self.backend == "ollama":
            return {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": self.max_tokens, "temperature": temperature},
            }

        return {
            "prompt": prompt,
            "n_predict": self.max_tokens,
            "temperature": temperature,
            "stop": ["User:", "System:"],
        }

    def _extract_text(self, result: dict) -> str:
        if self.backend == "ollama":
            return result.get("response", "")
        return result.get("content") or result.get("response") or result.get("text") or ""

    def _generate_with_cli(self, prompt: str, temperature: float = None) -> str:
        if not self.cli_path or not self.model_path:
            logger.debug("llama-cli sem caminho de binário/modelo configurado.")
            return None

        command = [
            self.cli_path,
            "-m", self.model_path,
            "-p", prompt,
            "-n", str(self.max_tokens),
            "-c", str(self.context_tokens),
            "-t", str(self.threads),
            "--temp", str(self.temperature if temperature is None else temperature),
            "--no-conversation",
            "--no-display-prompt",
        ]

        try:
            completed = self._run_command_with_timeout(command)
            stderr = (completed.stderr or "").strip()
            stdout = completed.stdout or ""
            if completed.returncode != 0:
                logger.warning(f"llama-cli retornou {completed.returncode}: {stderr[:500]}")
                return None
            if stderr:
                logger.debug(f"llama-cli stderr: {stderr[:500]}")
            cleaned = self._clean_cli_output(stdout)
            if not cleaned:
                logger.warning("llama-cli retornou stdout vazio.")
                return None
            return cleaned
        except FileNotFoundError:
            logger.debug("llama-cli não encontrado.")
            return None
        except subprocess.TimeoutExpired:
            logger.warning(f"llama-cli excedeu timeout de {self.timeout}s e foi finalizado.")
            return None
        except Exception as e:
            logger.error(f"Erro no llama-cli: {e}")
            return None

    def _run_command_with_timeout(self, command: list) -> subprocess.CompletedProcess:
        start_new_session = os.name != "nt"
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=start_new_session,
        )
        try:
            stdout, stderr = process.communicate(timeout=self.timeout)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired as exc:
            self._kill_process(process)
            try:
                stdout, stderr = process.communicate(timeout=2)
            except Exception:
                stdout, stderr = "", ""
            exc.output = stdout
            exc.stderr = stderr
            raise exc

    def _kill_process(self, process: subprocess.Popen) -> None:
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return
        except Exception as e:
            logger.warning(f"Falha ao matar llama-cli: {e}")

    def _clean_cli_output(self, output: str) -> str:
        ignored_prefixes = (
            "build      :",
            "model      :",
            "modalities :",
            "available commands:",
            "/exit",
            "/regen",
            "/clear",
            "/read",
            "/glob",
            "[ Prompt:",
        )
        lines = []
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(ignored_prefixes):
                continue
            if stripped in {"▄▄ ▄▄", "██ ██", "▀▀    ▀▀"}:
                continue
            if stripped.startswith(">"):
                continue
            lines.append(stripped)
        return " ".join(lines).strip() or None
