# apps/ai_tutor/backend/agents/tutor_agent.py
import os
from typing import List, Dict

class TutorAgent:
    def __init__(self):
        self.conversation_history: List[Dict[str, str]] = []

        # Modelo configurable por entorno; pon OPENAI_MODEL si quieres otro.
        # Por defecto uso un modelo actual y económico.
        self.model_new = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        # Si estás atado a la lib legacy, puedes fijar otro modelo aquí:
        self.model_legacy = os.getenv("OPENAI_MODEL_LEGACY", "gpt-3.5-turbo")

        # Detecta lib nueva vs legacy
        try:
            from openai import OpenAI  # >= 1.0
            self.client = OpenAI()     # usa OPENAI_API_KEY del entorno
            self.api_mode = "v1"
        except Exception:
            import openai              # < 1.0
            openai.api_key = os.getenv("OPENAI_API_KEY", "")
            self.openai = openai
            self.api_mode = "legacy"

        # Prompt de sistema
        self.system_prompt = (
            "Eres un tutor AI futurista con voz natural. "
            "Responde de forma concisa, clara y profesional, en español. "
            "Da pasos cortos y ejemplos breves cuando ayuden."
        )

        # Límite de turnos a mantener para contexto
        self.max_turns = 6

    def _build_messages(self, user_input: str) -> List[Dict[str, str]]:
        # Añade el turno actual del usuario al historial (en memoria)
        self.conversation_history.append({"role": "user", "content": user_input})

        # Toma solo el contexto reciente
        recent = self.conversation_history[-self.max_turns:]

        # Inserta system al inicio
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(recent)
        return messages

    def generate_response(self, user_input: str) -> str:
        user_input = (user_input or "").strip()
        if not user_input:
            return "¿En qué tema te gustaría que te ayude?"

        messages = self._build_messages(user_input)

        try:
            if self.api_mode == "v1":
                # Cliente nuevo (openai>=1.0)
                resp = self.client.chat.completions.create(
                    model=self.model_new,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=400,
                )
                ai_response = (resp.choices[0].message.content or "").strip()

            else:
                # Cliente legacy (openai<1.0)
                resp = self.openai.ChatCompletion.create(
                    model=self.model_legacy,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=400,
                )
                # Nota: en legacy el message es un dict
                ai_response = (resp.choices[0].message["content"] or "").strip()

            # Guarda respuesta en el historial
            self.conversation_history.append({"role": "assistant", "content": ai_response})
            return ai_response or "No tengo una respuesta en este momento."

        except Exception as e:
            # Devuelve texto legible para mostrar en el chat
            return f"Error del sistema: {e}"
