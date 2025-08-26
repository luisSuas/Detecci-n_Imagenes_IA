// static/js/script.js
document.addEventListener("DOMContentLoaded", () => {
  // ────────────────────────────────────────────────────────────
  // Referencias del DOM (tolerantes si algo no existe)
  // ────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const $$ = (sel) => document.querySelector(sel);

  const dropArea         = $("drop-area");
  const fileInput        = $("file-input");
  const browseButton     = $("browse-button");
  const preview          = $("preview");
  const canvas           = $("canvas");
  const analyzeButton    = $("analyze-button");
  const clearButton      = $("clear-button");

  const resultsSection   = $$(".results-section");
  const objectsTableBody = $("objects-table-body");
  const detailedAnalysis = $("detailed-analysis");
  const totalObjectsEl   = $("total-objects");
  const uniqueObjectsEl  = $("unique-objects");
  const confidenceEl     = $("confidence");
  const originalImage    = $("original-image");
  const processedImage   = $("processed-image");

  const loadingOverlay   = $$(".loading-overlay");
  const loadingStatus    = $("loading-status");

  const chatMessages     = $("chat-messages");
  const chatInput        = $("chat-input-text");
  const sendButton       = $("send-button");
  const voiceButton      = $("voice-button");

  const themeToggle      = $("theme-toggle");
  const languageSelect   = $("language-select");

  // Salir si el HTML no tiene lo básico (evita errores silenciosos)
  if (!dropArea || !fileInput || !analyzeButton) return;

  // ────────────────────────────────────────────────────────────
  // Estado
  // ────────────────────────────────────────────────────────────
  let currentFile = null;
  let recognition = null;
  let currentLanguage = localStorage.getItem("language") || "es";

  // ────────────────────────────────────────────────────────────
  // Traducciones
  // ────────────────────────────────────────────────────────────
  const t = {
    es: {
      alerts: {
        invalidFile: "Por favor, selecciona un archivo de imagen válido.",
        selectFirst: "Por favor, selecciona una imagen primero.",
        analyzing: "Procesando imagen...",
        analyzeError: (m) => "Error analizando la imagen: " + m,
        analyzeFallback: "Error analizando la imagen. Por favor, intenta con otra imagen.",
        connError: "Lo siento, ha ocurrido un error de conexión.",
        apiError: (m) => "Lo siento, ha ocurrido un error: " + m,
        imageCleared: "Imagen limpiada. Sube una nueva imagen para analizar.",
      },
      listening: "Escuchando...",
      chatPlaceholder: "Escribe tu mensaje...",
    },
    en: {
      alerts: {
        invalidFile: "Please select a valid image file.",
        selectFirst: "Please select an image first.",
        analyzing: "Processing image...",
        analyzeError: (m) => "Error analyzing image: " + m,
        analyzeFallback: "Error analyzing the image. Please try with another image.",
        connError: "Sorry, a connection error occurred.",
        apiError: (m) => "Sorry, an error occurred: " + m,
        imageCleared: "Image cleared. Upload a new image to analyze.",
      },
      listening: "Listening...",
      chatPlaceholder: "Type your message...",
    },
  };

  // ────────────────────────────────────────────────────────────
  // Idioma/Tema básicos (se asume index ya cambia todos los textos)
  // ────────────────────────────────────────────────────────────
  if (languageSelect) {
    languageSelect.addEventListener("change", (e) => {
      currentLanguage = e.target.value;
      localStorage.setItem("language", currentLanguage);
      if (chatInput) chatInput.placeholder = t[currentLanguage].chatPlaceholder;
      if (recognition) recognition.lang = currentLanguage === "es" ? "es-ES" : "en-US";
    });
    languageSelect.value = currentLanguage;
  }
  if (chatInput) chatInput.placeholder = t[currentLanguage].chatPlaceholder;

  if (themeToggle) {
    themeToggle.addEventListener("change", (e) => {
      if (e.target.checked) {
        document.body.classList.add("light-mode");
        localStorage.setItem("theme", "light");
      } else {
        document.body.classList.remove("light-mode");
        localStorage.setItem("theme", "dark");
      }
    });
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "light") {
      themeToggle.checked = true;
      document.body.classList.add("light-mode");
    }
  }

  // ────────────────────────────────────────────────────────────
  // Drag & Drop + File input
  // ────────────────────────────────────────────────────────────
  ["dragenter", "dragover", "dragleave", "drop"].forEach((ev) => {
    dropArea.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
  });
  ["dragenter", "dragover"].forEach((ev) => {
    dropArea.addEventListener(ev, () => dropArea.classList.add("highlight"));
  });
  ["dragleave", "drop"].forEach((ev) => {
    dropArea.addEventListener(ev, () => dropArea.classList.remove("highlight"));
  });

  dropArea.addEventListener("drop", (e) => handleFiles(e.dataTransfer.files));
  if (browseButton) browseButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => handleFiles(fileInput.files));

  function handleFiles(files) {
    if (!files || files.length === 0) return;
    const file = files[0];

    if (!file.type.startsWith("image/")) {
      alert(t[currentLanguage].alerts.invalidFile);
      return;
    }

    currentFile = file;
    const reader = new FileReader();
    reader.onload = (ev) => {
      if (preview) {
        preview.src = ev.target.result;
        preview.classList.remove("hidden");
      }
      if (originalImage) originalImage.src = ev.target.result;
      if (preview) {
        preview.onload = () => {
          canvas.width = preview.width;
          canvas.height = preview.height;
        };
      }
      analyzeButton.disabled = false;
    };
    reader.readAsDataURL(file);
  }

  // ────────────────────────────────────────────────────────────
  // Limpiar UI
  // ────────────────────────────────────────────────────────────
  if (clearButton) {
    clearButton.addEventListener("click", () => {
      if (preview) {
        preview.src = "";
        preview.classList.add("hidden");
      }
      if (originalImage) originalImage.src = "";
      if (processedImage) processedImage.src = "";
      currentFile = null;
      analyzeButton.disabled = true;

      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      if (resultsSection) resultsSection.classList.add("hidden");
      addMessageToChat(t[currentLanguage].alerts.imageCleared, "bot");
    });
  }

  // ────────────────────────────────────────────────────────────
  // Analizar imagen (con timeout y bloqueo de botón)
  // ────────────────────────────────────────────────────────────
  if (analyzeButton) {
    analyzeButton.addEventListener("click", analyzeImage);
  }

  async function analyzeImage() {
    if (!currentFile) {
      alert(t[currentLanguage].alerts.selectFirst);
      return;
    }

    setLoading(true, t[currentLanguage].alerts.analyzing);
    setAnalyzeEnabled(false);

    // Timeout de 45s
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 45000);

    try {
      const formData = new FormData();
      formData.append("file", currentFile);

      const resp = await fetch("/upload", {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

      // Manejo explícito de no-200
      if (!resp.ok) {
        let errMsg = `${resp.status} ${resp.statusText}`;
        try {
          const j = await resp.json();
          if (j && j.error) errMsg = j.error;
        } catch {}
        throw new Error(errMsg);
      }

      const data = await resp.json();
      if (data.error) throw new Error(data.error);

      // Dibuja la imagen de preview en el canvas (mismo tamaño)
      const ctx = canvas.getContext("2d");
      if (preview) ctx.drawImage(preview, 0, 0, canvas.width, canvas.height);

      // Simula cajas (visual) a partir de los conteos
      drawFakeBoxes(ctx, data.objects_detected);

      // Imagen "procesada"
      if (processedImage) processedImage.src = canvas.toDataURL("image/jpeg");

      showResults(data.objects_detected, data.analysis);
    } catch (err) {
      const msg = err.name === "AbortError"
        ? t[currentLanguage].alerts.connError
        : t[currentLanguage].alerts.analyzeError(err.message);
      alert(msg);
      addMessageToChat(t[currentLanguage].alerts.analyzeFallback, "bot");
    } finally {
      clearTimeout(timeoutId);
      setLoading(false);
      setAnalyzeEnabled(true);
    }
  }

  function setLoading(on, statusText) {
    if (!loadingOverlay) return;
    loadingOverlay.classList.toggle("hidden", !on);
    if (on && loadingStatus && statusText) loadingStatus.textContent = statusText;
  }
  function setAnalyzeEnabled(on) {
    analyzeButton.disabled = !on;
    if (browseButton) browseButton.disabled = !on;
    if (clearButton) clearButton.disabled = !on;
  }

  function drawFakeBoxes(ctx, objects) {
    const colors = ["#00ff9d", "#0cf", "#7024c4", "#ff00c8", "#ff9900"];
    let ci = 0;
    Object.entries(objects || {}).forEach(([name, count]) => {
      for (let i = 0; i < count; i++) {
        const x = Math.random() * Math.max(10, canvas.width - 120);
        const y = Math.random() * Math.max(30, canvas.height - 120);
        const w = 50 + Math.random() * 120;
        const h = 50 + Math.random() * 120;

        const color = colors[ci % colors.length];
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.strokeRect(x, y, w, h);

        ctx.fillStyle = "rgba(0,0,0,0.7)";
        ctx.fillRect(x, y - 24, Math.max(60, name.length * 9), 22);

        ctx.fillStyle = color;
        ctx.font = "16px Arial";
        ctx.fillText(name, x + 6, y - 8);
      }
      ci++;
    });
  }

  function showResults(objectsDetected, analysis) {
    // KPIs
    let total = 0;
    const unique = Object.keys(objectsDetected || {}).length;
    Object.values(objectsDetected || {}).forEach((c) => (total += c));

    if (totalObjectsEl) totalObjectsEl.textContent = String(total);
    if (uniqueObjectsEl) uniqueObjectsEl.textContent = String(unique);
    if (confidenceEl) confidenceEl.textContent = "85%"; // simulado

    // Tabla
    if (objectsTableBody) {
      objectsTableBody.innerHTML = "";
      Object.entries(objectsDetected || {}).forEach(([name, count]) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${escapeHtml(name)}</td>
          <td>${Number(count)}</td>
          <td>
            85%
            <div class="confidence-bar">
              <div class="confidence-fill" style="width:85%"></div>
            </div>
          </td>
        `;
        objectsTableBody.appendChild(tr);
      });
    }

    // Análisis
    if (detailedAnalysis) detailedAnalysis.textContent = analysis || "";

    // Mostrar sección
    if (resultsSection) resultsSection.classList.remove("hidden");

    // Mensaje de chat
    const msg =
      currentLanguage === "es"
        ? `He analizado tu imagen y detectado ${total} objetos. ¿En qué más puedo ayudarte?`
        : `I've analyzed your image and detected ${total} objects. How else can I help you?`;
    addMessageToChat(msg, "bot");
  }

  // ────────────────────────────────────────────────────────────
  // Chat + Voz
  // ────────────────────────────────────────────────────────────
  if (sendButton) {
    sendButton.addEventListener("click", sendMessage);
  }
  if (chatInput) {
    chatInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") sendMessage();
    });
  }

  function sendMessage() {
    const message = (chatInput?.value || "").trim();
    if (!message) return;

    addMessageToChat(message, "user");
    chatInput.value = "";

    // Timeout de 30s para chat
    const controller = new AbortController();
    const tid = setTimeout(() => controller.abort(), 30000);

    fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      signal: controller.signal,
    })
      .then(async (r) => {
        clearTimeout(tid);
        if (!r.ok) {
          let msg = `${r.status} ${r.statusText}`;
          try {
            const j = await r.json();
            if (j && j.error) msg = j.error;
          } catch {}
          throw new Error(msg);
        }
        return r.json();
      })
      .then((data) => {
        if (data.error) {
          addMessageToChat(t[currentLanguage].alerts.apiError(data.error), "bot");
        } else {
          addMessageToChat(data.response, "bot");
        }
      })
      .catch(() => {
        addMessageToChat(t[currentLanguage].alerts.connError, "bot");
      });
  }

  function addMessageToChat(text, who) {
    if (!chatMessages) return;
    const div = document.createElement("div");
    div.classList.add("message", `${who}-message`);
    div.textContent = text;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // Reconocimiento de voz (si está disponible)
  if (voiceButton && ("webkitSpeechRecognition" in window || "SpeechRecognition" in window)) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SR();
    recognition.continuous = false;
    recognition.lang = currentLanguage === "es" ? "es-ES" : "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    voiceButton.addEventListener("click", () => {
      if (voiceButton.classList.contains("recording")) {
        stopListening();
      } else {
        startListening();
      }
    });

    recognition.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      if (chatInput) chatInput.value = transcript;
      stopListening();
    };
    recognition.onerror = () => stopListening();
    recognition.onend = () => stopListening();
  } else if (voiceButton) {
    // Ocultar botón si no hay soporte
    voiceButton.style.display = "none";
  }

  function startListening() {
    try {
      if (!recognition) return;
      recognition.lang = currentLanguage === "es" ? "es-ES" : "en-US";
      recognition.start();
      voiceButton.classList.add("recording");
      voiceButton.setAttribute("aria-pressed", "true");
      voiceButton.innerHTML = '<i class="fas fa-stop"></i>';
      if (chatInput) chatInput.placeholder = t[currentLanguage].listening;
    } catch {}
  }
  function stopListening() {
    try { recognition?.stop(); } catch {}
    voiceButton.classList.remove("recording");
    voiceButton.removeAttribute("aria-pressed");
    voiceButton.innerHTML = '<i class="fas fa-microphone"></i>';
    if (chatInput) chatInput.placeholder = t[currentLanguage].chatPlaceholder;
  }

  // ────────────────────────────────────────────────────────────
  // Util
  // ────────────────────────────────────────────────────────────
  function escapeHtml(s = "") {
    return s
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
});
