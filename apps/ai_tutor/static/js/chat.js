// static/js/chat.js
class ChatInterface {
  constructor() {
    // Subruta inyectada desde el template ("" o algo como "/ai-tutor")
    this.BASE_PATH = window.APP_BASE || "";

    // HTTPS -> WSS, HTTP -> WS (evita Mixed Content)
    const WS_PROTO = location.protocol === "https:" ? "wss" : "ws";
    const WS_URL   = `${WS_PROTO}://${location.host}${this.BASE_PATH}/ws`;

    // Reusar una única conexión global para no abrir múltiples sockets
    if (
      !window.__AI_TUTOR_WS__ ||
      window.__AI_TUTOR_WS__.readyState === WebSocket.CLOSED ||
      window.__AI_TUTOR_WS__.readyState === WebSocket.CLOSING
    ) {
      window.__AI_TUTOR_WS__ = new WebSocket(WS_URL);
    }
    this.socket = window.__AI_TUTOR_WS__;

    // Cola para mensajes cuando el socket aún no está abierto
    this.pending = [];

    this.setupEventListeners();
    this.bindSocketLifecycle();
  }

  bindSocketLifecycle() {
    const setStatus = (t) => {
      const el = document.getElementById("status-text");
      if (el) el.textContent = t;
    };

    if (!this.socket) return;

    // Evitar múltiples binds si este archivo se carga más de una vez
    if (!this.socket.__chatBound__) {
      this.socket.addEventListener("open", () => {
        setStatus("Conectado - Listo para aprender");
        // Enviar lo pendiente
        while (this.pending.length && this.socket.readyState === WebSocket.OPEN) {
          this.socket.send(this.pending.shift());
        }
      });

      this.socket.addEventListener("close", () =>
        setStatus("Desconectado. Intentando reconectar...")
      );
      this.socket.addEventListener("error", () =>
        setStatus("Problema de conexión")
      );

      // Importante: NO añadimos onmessage aquí para no duplicar lo que maneja voice.js
      this.socket.__chatBound__ = true;
    }
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

    const payload = JSON.stringify({ type: "text", content: message });

    // Enviar por WS si está abierto; si no, encolar y mostrar estado
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(payload);
    } else {
      this.pending.push(payload);
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
