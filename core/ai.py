import json
import google.generativeai as genai
from config import Config

genai.configure(api_key=Config.GEMINI_API_KEY)

model = genai.GenerativeModel(Config.GEMINI_MODEL)

async def ai_intent(text):
    prompt = f"""
Retorne SOMENTE JSON:
{{
  "intent": "...",
  "action": null,
  "entity": null,
  "confidence": 0.5
}}

Mensagem:
"{text}"
"""
    res = model.generate_content(prompt)
    return json.loads(res.text)
