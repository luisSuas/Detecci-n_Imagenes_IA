class VoiceAssistant {
    constructor() {
        this.recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        this.isListening = false;
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.socket = new WebSocket(`ws://${window.location.host}/ws`);
        
        this.setupRecognition();
        this.setupUI();
        this.setupSocket();
    }
    
    setupRecognition() {
        this.recognition.lang = 'es-ES';
        this.recognition.interimResults = false;
        this.recognition.maxAlternatives = 1;
        
        this.recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            this.sendMessage(transcript);
        };
        
        this.recognition.onerror = (event) => {
            console.error('Error en reconocimiento:', event.error);
            this.updateStatus(`Error: ${event.error}`);
            this.stopListening();
        };
    }
    
    setupUI() {
        this.voiceBtn = document.getElementById('voice-btn');
        this.statusText = document.getElementById('status-text');
        this.voiceStatus = document.getElementById('voice-status');
        
        this.voiceBtn.addEventListener('click', () => {
            if (this.isListening) {
                this.stopListening();
            } else {
                this.startListening();
            }
        });
    }
    
    setupSocket() {
        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'text') {
                this.displayMessage(data.content, 'ai');
            } else if (data.type === 'audio') {
                this.playAudio(data.path);
            }
        };
    }
    
    startListening() {
        try {
            this.recognition.start();
            this.isListening = true;
            this.voiceBtn.classList.add('recording');
            this.voiceStatus.textContent = "Escuchando...";
            this.updateStatus("Reconociendo voz...");
        } catch (e) {
            console.error("Error al iniciar reconocimiento:", e);
        }
    }
    
    stopListening() {
        this.recognition.stop();
        this.isListening = false;
        this.voiceBtn.classList.remove('recording');
        this.voiceStatus.textContent = "Presiona para hablar";
        this.updateStatus("Listo");
    }
    
    sendMessage(text) {
        this.displayMessage(text, 'user');
        this.socket.send(JSON.stringify({
            type: 'text',
            content: text
        }));
    }
    
    displayMessage(text, sender) {
        const chatDisplay = document.getElementById('chat-display');
        const messageDiv = document.createElement('div');
        
        messageDiv.classList.add('message', `${sender}-message`);
        messageDiv.textContent = text;
        chatDisplay.appendChild(messageDiv);
        chatDisplay.scrollTop = chatDisplay.scrollHeight;
    }
    
    playAudio(audioPath) {
        const audio = new Audio(audioPath);
        audio.play();
        this.updateStatus("Reproduciendo respuesta...");
        
        audio.onended = () => {
            this.updateStatus("Listo");
        };
    }
    
    updateStatus(text) {
        this.statusText.textContent = text;
    }
}

// Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        new VoiceAssistant();
    } else {
        alert("Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.");
    }
});