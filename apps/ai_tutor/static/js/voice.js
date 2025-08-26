// static/js/voice.js
class VoiceAssistant {
  constructor() {
    // ── Reconocimiento de voz (fallback seguro)
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      alert("Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.");
      return;
    }

    this.recognition  = new SR();
    this.isListening  = false;
    this.audioContext = new (window.AudioContext || window.webkitAudioContext)();

    // Preferencia de salida de voz (ON por defecto)
    this.voiceEnabled = true;

    // Subruta inyectada desde el template ("" o p.ej. "/ai-tutor")
    this.BASE_PATH = window.APP_BASE || "";

    // URL del WebSocket (HTTPS→WSS)
    const WS_PROTO = location.protocol === "https:" ? "wss" : "ws";
    const WS_URL   = `${WS_PROTO}://${location.host}${this.BASE_PATH}/ws`;

    // Reutilizar socket global (compartido con chat.js)
    if (
      !window.__AI_TUTOR_WS__ ||
      window.__AI_TUTOR_WS__.readyState === WebSocket.CLOSED ||
      window.__AI_TUTOR_WS__.readyState === WebSocket.CLOSING
    ) {
      window.__AI_TUTOR_WS__ = new WebSocket(WS_URL);
    }
    this.socket  = window.__AI_TUTOR_WS__;
    this.pending = [];                 // cola de mensajes si WS aún no está OPEN

    // Control de audio/TTS para evitar voces dobles
    this.currentAudio      = null;     // <audio> en reproducción
    this.ttsFallbackTimer  = null;     // timer para TTS de respaldo

    this.setupRecognition();
    this.setupUI();
    this.bindSocketLifecycle(WS_URL);
  }

  // ────────────────────────────────────────────────────────────
  // Normalizador de URLs de audio (evita 404 en subrutas)
  // ────────────────────────────────────────────────────────────
  normalizeAudioUrl(audioPath) {
    const basePath = (window.APP_BASE || "");
    const origin   = window.location.origin;
    let p = (audioPath || "").toString().replace(/\\/g, "/");

    // Absolutas → tal cual
    if (/^https?:\/\//i.test(p)) return p;

    // Ya servidas por el static de la subapp
    if (p.startsWith("/ai-tutor-static/")) return origin + p;
    if (p.startsWith("ai-tutor-static/"))  return origin + basePath + "/" + p;

    // Mapea /static → /ai-tutor-static (cuando backend olvidó el prefijo público)
    if (p.startsWith("/static/")) {
      p = p.replace("/static/", "/ai-tutor-static/");
      return origin + basePath + p;
    }
    if (p.startsWith("static/")) {
      p = p.replace(/^static\//, "ai-tutor-static/");
      return origin + basePath + "/" + p;
    }

    // Rutas absolutas “raras”
    if (p.startsWith("/")) return origin + p;

    // Relativa genérica → cuélgala de la subruta
    return origin + basePath + "/" + p;
  }

  // ────────────────────────────────────────────────────────────
  // Reconocimiento de voz
  // ────────────────────────────────────────────────────────────
  setupRecognition() {
    this.recognition.lang            = "es-ES";
    this.recognition.interimResults  = false;
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

  // ────────────────────────────────────────────────────────────
  // UI
  // ────────────────────────────────────────────────────────────
  setupUI() {
    this.voiceBtn    = document.getElementById("voice-btn");
    this.statusText  = document.getElementById("status-text");
    this.voiceStatus = document.getElementById("voice-status");

    if (this.voiceBtn) {
      this.voiceBtn.addEventListener("click", async () => {
        // Algunos navegadores exigen interacción para reproducir audio
        try { await this.audioContext.resume(); } catch (_) {}

        if (this.isListening) this.stopListening();
        else                  this.startListening();
      });
    }
  }

  // ────────────────────────────────────────────────────────────
  // WebSocket (ciclo de vida compartido; no pisar handlers)
  // ────────────────────────────────────────────────────────────
  bindSocketLifecycle(WS_URL) {
    if (!this.socket) return;

    if (!this.socket.__voiceBound__) {
      this.socket.addEventListener("open", () => {
        this.updateStatus("Conectado - Listo para aprender");
        // Enviar cola pendiente
        while (this.pending.length && this.socket.readyState === WebSocket.OPEN) {
          this.socket.send(this.pending.shift());
        }
      });

      this.socket.addEventListener("message", (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "text") {
            this.displayMessage(data.content, "ai");

            // Programar fallback TTS si no llega audio del servidor
            if (this.voiceEnabled) {
              clearTimeout(this.ttsFallbackTimer);
              this.ttsFallbackTimer = setTimeout(() => {
                this.speakClient(data.content);
              }, 900);
            }
          }

          else if (data.type === "audio") {
            // Llega audio servidor → cancelar cualquier TTS y reproducir SOLO audio
            clearTimeout(this.ttsFallbackTimer);
            this.cancelTTS();
            if (this.voiceEnabled) this.playAudio(data.path);
          }

        } catch {
          // Mensajes no-JSON: ignorar
        }
      });

      this.socket.addEventListener("error", () => {
        this.updateStatus("Problema de conexión");
      });

      this.socket.addEventListener("close", () => {
        this.updateStatus("Desconectado. Reintentando...");
        this.scheduleReconnect(WS_URL);
      });

      this.socket.__voiceBound__ = true;
    }
  }

  // Única rutina de reconexión
  scheduleReconnect(WS_URL) {
    if (window.__AI_TUTOR_WS_RECONNECTING__) return;
    window.__AI_TUTOR_WS_RECONNECTING__ = true;

    setTimeout(() => {
      try {
        if (window.__AI_TUTOR_WS__ && window.__AI_TUTOR_WS__.readyState === WebSocket.OPEN) {
          window.__AI_TUTOR_WS_RECONNECTING__ = false;
          this.socket = window.__AI_TUTOR_WS__;
          return;
        }
        window.__AI_TUTOR_WS__ = new WebSocket(WS_URL);
        this.socket = window.__AI_TUTOR_WS__;
        this.bindSocketLifecycle(WS_URL);
      } catch (e) {
        console.error("Reconexión WS falló:", e);
      } finally {
        const clear = () => { window.__AI_TUTOR_WS_RECONNECTING__ = false; };
        this.socket.addEventListener("open", clear, { once: true });
        setTimeout(clear, 2000);
      }
    }, 1500);
  }

  // ────────────────────────────────────────────────────────────
  // Comandos para activar/desactivar voz
  // ────────────────────────────────────────────────────────────
  maybeToggleVoiceByCommand(textRaw) {
    const text = (textRaw || "").toLowerCase();

    const disableTriggers = ["solo texto","sin voz","mute","silencio","modo texto"];
    const enableTriggers  = ["con voz","activa voz","modo voz","leer en voz alta"];

    if (disableTriggers.some(k => text.includes(k))) {
      this.voiceEnabled = false;
      this.stopAllSpeech();
      this.updateStatus("Modo texto activado");
      return true;
    }
    if (enableTriggers.some(k => text.includes(k))) {
      this.voiceEnabled = true;
      this.updateStatus("Modo voz activado");
      return true;
    }
    return false;
  }

  // ────────────────────────────────────────────────────────────
  // Flujo de conversación
  // ────────────────────────────────────────────────────────────
  startListening() {
    try {
      this.recognition.start();
      this.isListening = true;
      if (this.voiceBtn)    this.voiceBtn.classList.add("recording");
      if (this.voiceStatus) this.voiceStatus.textContent = "Escuchando...";
      this.updateStatus("Reconociendo voz...");
    } catch (e) {
      console.error("Error al iniciar reconocimiento:", e);
    }
  }

  stopListening() {
    try { this.recognition.stop(); } catch (_) {}
    this.isListening = false;
    if (this.voiceBtn)    this.voiceBtn.classList.remove("recording");
    if (this.voiceStatus) this.voiceStatus.textContent = "Presiona para hablar";
    this.updateStatus("Listo");
  }

  sendMessage(text) {
    // Procesa comandos de voz ON/OFF
    if (this.maybeToggleVoiceByCommand(text)) {
      this.displayMessage(text, "user");
      return;
    }

    this.displayMessage(text, "user");

    const payload = JSON.stringify({ type: "text", content: text });
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(payload);
    } else {
      this.pending.push(payload);
      this.updateStatus("Reconectando socket…");
    }
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

  // ────────────────────────────────────────────────────────────
  // Audio del servidor (sin voces dobles)
  // ────────────────────────────────────────────────────────────
  playAudio(audioPath) {
    if (!audioPath) return;

    const url = this.normalizeAudioUrl(audioPath);

    // Corta todo lo que esté sonando (incluye TTS)
    this.stopAllSpeech();

    this.currentAudio = new Audio(url);

    // Si el recurso falla, haz TTS con el último texto del asistente
    this.currentAudio.onerror = () => {
      const txt = this.extractLastAssistantText();
      if (txt) this.speakClient(txt);
    };

    this.currentAudio
      .play()
      .then(() => this.updateStatus("Reproduciendo respuesta..."))
      .catch(() => this.updateStatus("Pulsa el botón para permitir audio"));

    this.currentAudio.onended = () => {
      this.updateStatus("Listo");
      this.currentAudio = null;
    };
  }

  // Último mensaje del asistente en pantalla (para TTS fallback)
  extractLastAssistantText() {
    const chatDisplay = document.getElementById("chat-display");
    if (!chatDisplay) return "";
    const msgs = [...chatDisplay.querySelectorAll(".ai-message")];
    return (msgs.at(-1)?.textContent || "").trim();
  }

  // ────────────────────────────────────────────────────────────
  // TTS local (fallback)
  // ────────────────────────────────────────────────────────────
  speakClient(text) {
    if (!text || !("speechSynthesis" in window)) return;

    // Corta cualquier audio previo
    this.stopAudioOnly();

    // Cancela cola previa de TTS
    window.speechSynthesis.cancel();

    const utter = new SpeechSynthesisUtterance(text);
    utter.lang  = "es-ES";
    utter.rate  = 1.0;
    utter.pitch = 1.0;

    const pickVoice = () => {
      const voices = window.speechSynthesis.getVoices() || [];
      const preferred =
        voices.find(v => /es[-_](ES|MX|US)/i.test(v.lang)) ||
        voices.find(v => /spanish/i.test(v.name));
      if (preferred) utter.voice = preferred;
      window.speechSynthesis.speak(utter);
      this.updateStatus("Reproduciendo respuesta (TTS)...");
    };

    if (window.speechSynthesis.getVoices().length === 0) {
      const handler = () => { pickVoice(); window.speechSynthesis.onvoiceschanged = null; };
      window.speechSynthesis.onvoiceschanged = handler;
      setTimeout(pickVoice, 250);
    } else {
      pickVoice();
    }

    utter.onend = () => this.updateStatus("Listo");
  }

  // ────────────────────────────────────────────────────────────
  // Utilidades de control de audio/TTS
  // ────────────────────────────────────────────────────────────
  cancelTTS() {
    try { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); } catch (_) {}
  }

  stopAudioOnly() {
    try {
      if (this.currentAudio) {
        this.currentAudio.pause();
        this.currentAudio.src = "";
        this.currentAudio = null;
      }
    } catch (_) {}
  }

  stopAllSpeech() {
    clearTimeout(this.ttsFallbackTimer);
    this.cancelTTS();
    this.stopAudioOnly();
  }

  updateStatus(text) {
    const el = this.statusText || document.getElementById("status-text");
    if (el) el.textContent = text;
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
