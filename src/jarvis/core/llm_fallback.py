import requests
import json
import logging

logger = logging.getLogger(__name__)

class LLMFallbackEngine:
    def __init__(self):
        # Default to localhost, but allows for docker internal networking if needed
        # In a real Docker setup, this might be "http://host.docker.internal:11434"
        # or specific IP, but localhost covers the requirement for "validar Ollama rodando no host".
        self.url = "http://localhost:11434/api/generate"
        self.model = "tinyllama"

    def is_available(self) -> bool:
        """Checa se o Ollama está respondendo"""
        try:
            # Tenta endpoint raiz ou tags para verificar vida
            requests.get("http://localhost:11434/", timeout=1)
            return True
        except:
            return False

    def generate_chat_response(self, text: str) -> str:
        """Gera resposta de chat livre (não-JSON)"""
        prompt = f"""
        System: Você é Jarvis do Cerrado, um assistente útil e engraçado com sotaque goiano leve. Responda de forma curta.
        User: {text}
        Assistant:
        """

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 150, "temperature": 0.7}
        }

        try:
            response = requests.post(self.url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except requests.exceptions.ConnectionError:
            logger.debug("Ollama offline.")
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

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 120, "temperature": 0.1}
        }

        try:
            response = requests.post(self.url, json=payload, timeout=15)
            response.raise_for_status()
            result = response.json()

            # Ollama returns the generated text in 'response' field
            generated_text = result.get("response", "")

            # Clean up potential markdown code blocks
            generated_text = generated_text.replace("```json", "").replace("```", "").strip()

            return json.loads(generated_text)

        except requests.exceptions.ConnectionError:
            # Log as debug to reduce noise, as Ollama might simply be offline
            logger.debug("Ollama não está acessível (ConnectionError) - Ignorando fallback local.")
            return None
        except json.JSONDecodeError:
            logger.warning(f"Falha ao decodificar JSON do LLM: {generated_text}")
            return None
        except Exception as e:
            logger.error(f"Erro no LLMFallbackEngine (Interpret): {e}")
            return None
