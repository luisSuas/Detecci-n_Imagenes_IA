from typing import List, Dict

class ChatHistory:
    def __init__(self):
        self.messages = [{
            "role": "system",
            "content": "Eres un tutor virtual experto en múltiples materias académicas."
        }]
    
    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})
    
    def add_assistant_message(self, content: str):
        self.messages.append({"role": "assistant", "content": content})
    
    def get_messages(self) -> List[Dict]:
        return self.messages
    
    def clear_history(self):
        self.messages = self.messages[:1]