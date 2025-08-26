class ChatInterface {
  constructor() {
    // Subruta inyectada desde el template ("" o algo como "/ai-tutor")
    this.BASE_PATH = window.APP_BASE || "";

    // HTTPS -> WSS, HTTP -> WS
    const WS_PROTO = location.protocol === "https:" ? "wss" : "ws";
    const WS_URL   = `${WS_PROTO}://${location.host}${this.BASE_PATH}/ws`;

    // Reusar una única conexión compartida para evitar múltiples sockets
    window.__AI_TUTOR_WS__ = window.__AI_TUTOR_WS__ || new WebSocket(WS_URL);
    this.socket = window.__AI_TUTOR_WS__;

    this.setupEventListeners();
    this.setupSocketSideEffects();
  }

  setupSocketSideEffects() {
    const setStatus = (t) => {
      const el = document.getElementById("status-text");
      if (el) el.textContent = t;
    };

    if (!this.socket) return;

    this.socket.addEventListener("open",  () => setStatus("Conectado - Listo para aprender"));
    this.socket.addEventListener("close", () => setStatus("Desconectado. Intentando reconectar..."));
    this.socket.addEventListener("error", () => setStatus("Problema de conexión"));
    // NOTA: no añadimos onmessage aquí para no duplicar lo que ya maneja voice.js
  }

  setupEventListeners() {
    const sendBtn   = document.getElementById("send-btn");
    const userInput = document.getElementById("user-input");

    if (sendBtn) sendBtn.addEventListener("click", () => this.sendTextMessage());
    if (userInput) {
      userInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") this.sendTextMessage();
      });
    }
  }

  sendTextMessage() {
    const input = document.getElementById("user-input");
    if (!input) return;

    const message = input.value.trim();
    if (!message) return;

    // Mostrar mensaje del usuario en la UI
    this.displayMessage(message, "user");

    // Enviar por WS si está abierto; si no, mostrar estado (reconexión la maneja voice.js)
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "text", content: message }));
    } else {
      const el = document.getElementById("status-text");
      if (el) el.textContent = "Reconectando socket…";
    }

    input.value = "";
  }

  displayMessage(text, sender) {
    const chatDisplay = document.getElementById("chat-display");
    if (!chatDisplay) return;

    const messageDiv = document.createElement("div");
    messageDiv.classList.add("message", `${sender}-message`);
    messageDiv.textContent = text;

    chatDisplay.appendChild(messageDiv);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;
  }
}

// Inicializar cuando el DOM esté listo
document.addEventListener("DOMContentLoaded", () => {
  new ChatInterface();
});
