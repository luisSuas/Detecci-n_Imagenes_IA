class VoiceAssistant {
  constructor() {
    // Fallbacks seguros
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      alert("Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.");
      return;
    }

    this.recognition = new SR();
    this.isListening = false;
    this.audioContext = new (window.AudioContext || window.webkitAudioContext)();

    // === Construcción de URL del WebSocket (HTTPS -> WSS) y soporta subruta ===
    this.BASE_PATH = (window.APP_BASE || ""); // ej: "" o "/ai-tutor"
    const WS_PROTO = (location.protocol === "https:") ? "wss" : "ws";
    const WS_URL   = `${WS_PROTO}://${location.host}${this.BASE_PATH}/ws`;

    // Reutiliza una conexión global si ya existe (voz/chat comparten)
    window.__AI_TUTOR_WS__ = window.__AI_TUTOR_WS__ || new WebSocket(WS_URL);
    this.socket = window.__AI_TUTOR_WS__;

    this.setupRecognition();
    this.setupUI();
    this.setupSocket();
  }

  setupRecognition() {
    this.recognition.lang = "es-ES";
    this.recognition.interimResults = false;
    this.recognition.maxAlternatives = 1;

    this.recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      this.sendMessage(transcript);
    };

    this.recognition.onerror = (event) => {
      console.error("Error en reconocimiento:", event.error);
      this.updateStatus(`Error: ${event.error}`);
      this.stopListening();
    };
  }

  setupUI() {
    this.voiceBtn    = document.getElementById("voice-btn");
    this.statusText  = document.getElementById("status-text");
    this.voiceStatus = document.getElementById("voice-status");

    this.voiceBtn.addEventListener("click", async () => {
      // Algunos navegadores exigen interacción para reproducir audio
      try { await this.audioContext.resume(); } catch (_) {}

      if (this.isListening) {
        this.stopListening();
      } else {
        this.startListening();
      }
    });
  }

  setupSocket() {
    if (!this.socket) return;

    this.socket.onopen = () => {
      this.updateStatus("Conectado - Listo para aprender");
    };

    this.socket.onclose = () => {
      this.updateStatus("Desconectado. Reintentando...");
      // Reconexión ligera tras 1.5s
      setTimeout(() => {
        try {
          const WS_PROTO = (location.protocol === "https:") ? "wss" : "ws";
          const WS_URL   = `${WS_PROTO}://${location.host}${this.BASE_PATH}/ws`;
          window.__AI_TUTOR_WS__ = new WebSocket(WS_URL);
          this.socket = window.__AI_TUTOR_WS__;
          this.setupSocket();
        } catch (e) {
          console.error("Reconexión WS falló:", e);
        }
      }, 1500);
    };

    this.socket.onerror = () => {
      this.updateStatus("Problema de conexión");
    };

    this.socket.onmessage = (event) => {
      // El backend envía JSON con {type: "text"|"audio", ...}
      try {
        const data = JSON.parse(event.data);
        if (data.type === "text") {
          this.displayMessage(data.content, "ai");
        } else if (data.type === "audio") {
          this.playAudio(data.path);
        }
      } catch (e) {
        console.warn("Mensaje WS no-JSON (ignorado):", event.data);
      }
    };
  }

  startListening() {
    try {
      this.recognition.start();
      this.isListening = true;
      this.voiceBtn.classList.add("recording");
      this.voiceStatus.textContent = "Escuchando...";
      this.updateStatus("Reconociendo voz...");
    } catch (e) {
      console.error("Error al iniciar reconocimiento:", e);
    }
  }

  stopListening() {
    try { this.recognition.stop(); } catch (_) {}
    this.isListening = false;
    this.voiceBtn.classList.remove("recording");
    this.voiceStatus.textContent = "Presiona para hablar";
    this.updateStatus("Listo");
  }

  sendMessage(text) {
    this.displayMessage(text, "user");

    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      this.updateStatus("Reconectando socket…");
      return;
    }

    this.socket.send(JSON.stringify({
      type: "text",
      content: text
    }));
  }

  displayMessage(text, sender) {
    const chatDisplay = document.getElementById("chat-display");
    const messageDiv  = document.createElement("div");

    messageDiv.classList.add("message", `${sender}-message`);
    messageDiv.textContent = text;
    chatDisplay.appendChild(messageDiv);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;
  }

  playAudio(audioPath) {
    if (!audioPath) return;

    // Normalizamos a URL absoluta; respeta subruta si viene relativa
    let url = audioPath;
    if (!/^https?:\/\//i.test(audioPath)) {
      if (audioPath.startsWith("/")) {
        url = new URL(audioPath, location.origin).toString();
      } else {
        // relativo: lo colgamos de la subruta si existe
        const base = this.BASE_PATH.replace(/\/$/, "");
        url = new URL(`${base ? base + "/" : "/"}${audioPath}`, location.origin).toString();
      }
    }

    const audio = new Audio(url);
    // En caso de política de autoplay estricta
    audio.play().then(() => {
      this.updateStatus("Reproduciendo respuesta...");
    }).catch(() => {
      this.updateStatus("Pulsa el botón para permitir audio");
    });

    audio.onended = () => {
      this.updateStatus("Listo");
    };
  }

  updateStatus(text) {
    if (this.statusText) this.statusText.textContent = text;
  }
}

// Inicializar cuando el DOM esté listo
document.addEventListener("DOMContentLoaded", () => {
  if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
    new VoiceAssistant();
  } else {
    alert("Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.");
  }
});
