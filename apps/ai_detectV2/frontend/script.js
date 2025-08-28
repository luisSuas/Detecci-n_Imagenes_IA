// static/js/script.js
document.addEventListener("DOMContentLoaded", () => {
  // ────────────────────────────────────────────────────────────
  // Prefijo del app montado (p.ej. "/ai-detect-v2")
  // ────────────────────────────────────────────────────────────
  const API_BASE = (() => {
    const seg = window.location.pathname.split("/").filter(Boolean)[0] || "";
    return seg ? `/${seg}` : "";
  })();
  const api = (p) => `${API_BASE}${p.startsWith("/") ? p : `/${p}`}`;

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
  if (!dropArea || !fileInput || !analyzeButton || !canvas) return;

  // ────────────────────────────────────────────────────────────
  // Estado
  // ────────────────────────────────────────────────────────────
  let currentFile = null;
  let recognition = null;
  let currentLanguage = localStorage.getItem("language") || "es";

  // ────────────────────────────────────────────────────────────
  // Traducciones (UI + alerts)
  // ────────────────────────────────────────────────────────────
  const t = {
    es: {
      // Textos de UI
      title: "Sistema de Detección de Objetos con IA",
      subtitle: "Carga una imagen para analizar su contenido con inteligencia artificial",
      instructionsTitle: "Instrucciones de uso",
      instruction1: "Arrastra una imagen o haz clic en \"Seleccionar archivo\"",
      instruction2: "Haz clic en \"Analizar Imagen\" para procesarla con IA",
      instruction3: "Revisa los objetos detectados y el análisis detallado",
      instruction4: "Interactúa con el chatbot mediante texto o voz",
      instruction5: "Para analizar otra imagen, haz clic en \"Limpiar\"",
      instruction6: "Usa los controles en la esquina superior derecha para cambiar entre tema claro/oscuro e idioma",
      dropText: "Arrastra y suelta tu imagen aquí",
      orText: "o",
      browseText: "Seleccionar archivo",
      analyzeText: "Analizar Imagen",
      clearText: "Limpiar",
      resultsTitle: "Resultados del Análisis",
      objectsLabel: "Objetos Detectados",
      typesLabel: "Tipos Diferentes",
      accuracyLabel: "Precisión Media",
      originalImageLabel: "Imagen Original",
      processedImageLabel: "Imagen con Detección",
      objectsTitle: "Objetos Detectados",
      objectHeader: "Objeto",
      quantityHeader: "Cantidad",
      accuracyHeader: "Precisión",
      analysisTitle: "Análisis Detallado",
      assistantTitle: "Asistente por Voz",
      sendText: "Enviar",
      footerText: "Sistema de Detección de Objetos con IA",
      loadingText: "Analizando con IA...",
      welcomeMessage:
        "¡Hola! Soy tu asistente de IA. Puedo ayudarte a analizar imágenes. Sube una imagen y haz clic en \"Analizar\" para comenzar.",
      languageLabel: "Idioma",
      themeLabel: "Tema",

      // Alerts / placeholders
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
      // UI
      title: "AI Object Detection System",
      subtitle: "Upload an image to analyze its content with artificial intelligence",
      instructionsTitle: "Usage Instructions",
      instruction1: "Drag an image or click on \"Select file\"",
      instruction2: "Click on \"Analyze Image\" to process it with AI",
      instruction3: "Review the detected objects and detailed analysis",
      instruction4: "Interact with the chatbot via text or voice",
      instruction5: "To analyze another image, click on \"Clear\"",
      instruction6: "Use the controls in the top right corner to switch between light/dark theme and language",
      dropText: "Drag and drop your image here",
      orText: "or",
      browseText: "Select file",
      analyzeText: "Analyze Image",
      clearText: "Clear",
      resultsTitle: "Analysis Results",
      objectsLabel: "Objects Detected",
      typesLabel: "Different Types",
      accuracyLabel: "Average Accuracy",
      originalImageLabel: "Original Image",
      processedImageLabel: "Image with Detection",
      objectsTitle: "Detected Objects",
      objectHeader: "Object",
      quantityHeader: "Quantity",
      accuracyHeader: "Accuracy",
      analysisTitle: "Detailed Analysis",
      assistantTitle: "Voice Assistant",
      sendText: "Send",
      footerText: "AI Object Detection System",
      loadingText: "Analyzing with AI...",
      welcomeMessage:
        "Hello! I'm your AI assistant. I can help you analyze images. Upload an image and click \"Analyze\" to get started.",
      languageLabel: "Language",
      themeLabel: "Theme",

      // Alerts / placeholders
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
  // Aplicar idioma a toda la UI
  // ────────────────────────────────────────────────────────────
  function applyLanguage(lang) {
    currentLanguage = lang;
    document.documentElement.lang = lang;

    const map = {
      "title-text": t[lang].title,
      "subtitle-text": t[lang].subtitle,
      "instructions-title": t[lang].instructionsTitle,
      "instruction-1": t[lang].instruction1,
      "instruction-2": t[lang].instruction2,
      "instruction-3": t[lang].instruction3,
      "instruction-4": t[lang].instruction4,
      "instruction-5": t[lang].instruction5,
      "instruction-6": t[lang].instruction6,
      "drop-text": t[lang].dropText,
      "or-text": t[lang].orText,
      "browse-text": t[lang].browseText,
      "analyze-text": t[lang].analyzeText,
      "clear-text": t[lang].clearText,
      "results-title": t[lang].resultsTitle,
      "objects-label": t[lang].objectsLabel,
      "types-label": t[lang].typesLabel,
      "accuracy-label": t[lang].accuracyLabel,
      "original-image-label": t[lang].originalImageLabel,
      "processed-image-label": t[lang].processedImageLabel,
      "objects-title": t[lang].objectsTitle,
      "object-header": t[lang].objectHeader,
      "quantity-header": t[lang].quantityHeader,
      "accuracy-header": t[lang].accuracyHeader,
      "analysis-title": t[lang].analysisTitle,
      "assistant-title": t[lang].assistantTitle,
      "send-text": t[lang].sendText,
      "footer-text": t[lang].footerText,
      "loading-text": t[lang].loadingText,
      "welcome-message": t[lang].welcomeMessage,
      "language-label": t[lang].languageLabel,
      "theme-label": t[lang].themeLabel,
    };

    Object.entries(map).forEach(([id, text]) => {
      const el = $(id);
      if (el && typeof text === "string") el.textContent = text;
    });

    if (chatInput) chatInput.placeholder = t[lang].chatPlaceholder;
    if (recognition) recognition.lang = lang === "es" ? "es-ES" : "en-US";
    if (languageSelect) languageSelect.value = lang;

    localStorage.setItem("language", lang);
  }

  // Selector de idioma → usar applyLanguage
  if (languageSelect) {
    languageSelect.addEventListener("change", (e) => applyLanguage(e.target.value));
    applyLanguage(currentLanguage);
  } else {
    // fallback si no hay selector
    applyLanguage(currentLanguage);
  }

  // ────────────────────────────────────────────────────────────
  // Tema (se mantiene igual)
  // ────────────────────────────────────────────────────────────
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

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 45000);

    try {
      const formData = new FormData();
      formData.append("file", currentFile);

      const resp = await fetch(api(`/upload?lang=${encodeURIComponent(currentLanguage)}`), {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

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

      const ctx = canvas.getContext("2d");
      if (preview) ctx.drawImage(preview, 0, 0, canvas.width, canvas.height);

      drawFakeBoxes(ctx, data.objects_detected);
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
    let total = 0;
    const unique = Object.keys(objectsDetected || {}).length;
    Object.values(objectsDetected || {}).forEach((c) => (total += c));

    if (totalObjectsEl) totalObjectsEl.textContent = String(total);
    if (uniqueObjectsEl) uniqueObjectsEl.textContent = String(unique);
    if (confidenceEl) confidenceEl.textContent = "85%"; // simulado

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

    if (detailedAnalysis) detailedAnalysis.textContent = analysis || "";
    if (resultsSection) resultsSection.classList.remove("hidden");

    const msg =
      currentLanguage === "es"
        ? `He analizado tu imagen y detectado ${total} objetos. ¿En qué más puedo ayudarte?`
        : `I've analyzed your image and detected ${total} objects. How else can I help you?`;
    addMessageToChat(msg, "bot");
  }

  // ────────────────────────────────────────────────────────────
  // Chat + Voz
  // ────────────────────────────────────────────────────────────
  if (sendButton) sendButton.addEventListener("click", sendMessage);
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

    const controller = new AbortController();
    const tid = setTimeout(() => controller.abort(), 30000);

    fetch(api(`/chat?lang=${encodeURIComponent(currentLanguage)}`), {
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
