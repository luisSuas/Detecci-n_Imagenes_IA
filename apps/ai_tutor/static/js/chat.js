class ChatInterface {
    constructor() {
        this.socket = new WebSocket(`ws://${window.location.host}/ws`);
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        const sendBtn = document.getElementById('send-btn');
        const userInput = document.getElementById('user-input');
        
        sendBtn.addEventListener('click', () => this.sendTextMessage());
        
        userInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.sendTextMessage();
            }
        });
    }
    
    sendTextMessage() {
        const input = document.getElementById('user-input');
        const message = input.value.trim();
        
        if (message) {
            this.displayMessage(message, 'user');
            this.socket.send(JSON.stringify({
                type: 'text',
                content: message
            }));
            input.value = '';
        }
    }
    
    displayMessage(text, sender) {
        const chatDisplay = document.getElementById('chat-display');
        const messageDiv = document.createElement('div');
        
        messageDiv.classList.add('message', `${sender}-message`);
        messageDiv.textContent = text;
        chatDisplay.appendChild(messageDiv);
        chatDisplay.scrollTop = chatDisplay.scrollHeight;
    }
}

// Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    new ChatInterface();
});