import openai
import os

class TutorAgent:
    def __init__(self):
        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.conversation_history = []
    
    def generate_response(self, user_input: str) -> str:
        self.conversation_history.append({"role": "user", "content": user_input})
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Eres un tutor AI futurista con voz natural. Responde de forma concisa y profesional."},
                    *self.conversation_history[-6:]  # Mantener contexto reciente
                ],
                temperature=0.7
            )
            
            ai_response = response.choices[0].message['content']
            self.conversation_history.append({"role": "assistant", "content": ai_response})
            return ai_response
            
        except Exception as e:
            return f"Error del sistema: {str(e)}"