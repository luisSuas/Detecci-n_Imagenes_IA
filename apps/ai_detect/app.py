from flask import Flask, render_template, request, jsonify, send_file
import os
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime
import json
import io
import hashlib
import re
from dotenv import load_dotenv
from pathlib import Path

# ========= Cargar .env =========
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# Acepta 'yolo' | 'llm' | 'auto' (compat: si no se define, asumimos 'yolo')
DETECTOR_MODE = os.getenv("DETECTOR_MODE", "yolo").strip().lower()

# Modelos por tarea (con retrocompatibilidad a OPENAI_MODEL)
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
OPENAI_STT_MODEL  = os.getenv("OPENAI_STT_MODEL",  "gpt-4o-mini-transcribe")
OPENAI_TTS_MODEL  = os.getenv("OPENAI_TTS_MODEL",  "gpt-4o-mini-tts")

# Mantener compatibilidad con código que usa OPENAI_MODEL
OPENAI_MODEL = OPENAI_CHAT_MODEL

# ========= OpenAI Client =========
from openai import OpenAI
client = None
if OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        print("✅ OpenAI client listo")
        print(f"🧠 Chat model: {OPENAI_CHAT_MODEL}")
        print(f"🗣️  STT model:  {OPENAI_STT_MODEL}")
        print(f"🔊 TTS model:  {OPENAI_TTS_MODEL}")
    except Exception as e:
        print(f"❌ No se pudo iniciar OpenAI client: {e}")
else:
    print("⚠️ Falta OPENAI_API_KEY en el entorno (.env)")

# ========= Memoria / Estado =========
last_result = None
chat_progress = {}
results_by_filename = {}

# Voz global (persistente en el proceso)
SPEECH_ENABLED = True  # voz activada por defecto

# === Memoria simple para transcripción en vivo (por sesión) ===
# Estructura: { sid: { seq:int -> texto:str }, ... }
LIVE_TRANSCRIPTS = {}

# ========= Helpers =========
def _compact_result_for_llm(result: dict) -> dict:
    if not result or not isinstance(result, dict):
        return {}
    summary = {
        "filename": result.get("filename"),
        "timestamp": result.get("timestamp"),
        "resumen_inspeccion": {
            "prioridad_global": result.get("resumen_inspeccion", {}).get("prioridad_global"),
            "urgencia_global": result.get("resumen_inspeccion", {}).get("urgencia_global"),
            "zona": result.get("resumen_inspeccion", {}).get("zona") or result.get("resumen_inspeccion", {}).get("lugar"),
            "detecciones": result.get("resumen_inspeccion", {}).get("detecciones"),
            "acciones_recomendadas_globales": result.get("resumen_inspeccion", {}).get("acciones_recomendadas_globales"),
        },
        "reporte_incidencia": [],
        "solucion": [],
    }
    if isinstance(result.get("reporte_incidencia"), list):
        for r in result["reporte_incidencia"][:8]:
            summary["reporte_incidencia"].append({
                "problema": r.get("problema"),
                "prioridad": r.get("prioridad"),
                "confianza": r.get("confianza"),
                "descripcion": r.get("descripcion")
            })
    if isinstance(result.get("solucion"), list):
        for s in result["solucion"][:8]:
            summary["solucion"].append({
                "problema": s.get("problema"),
                "pasos": s.get("pasos", [])[:5],
                "workers_detalle": s.get("workers_detalle", {})
            })
    if not summary["reporte_incidencia"] and isinstance(result.get("detections"), list):
        for d in result["detections"][:6]:
            summary["reporte_incidencia"].append({
                "problema": d.get("class"),
                "prioridad": d.get("severity"),
                "confianza": round(float(d.get("confidence", 0.0)) * 100, 1),
                "descripcion": d.get("description"),
            })
    return summary

def _friendly_name(cls: str) -> str:
    """Nombre legible para clases del detector."""
    mapping = {
        'filtracion_pared': 'enchufe por cambiar',
        'fuga_techo': 'fuga en techo',
        'tuberia_rota': 'tubería rota',
        'equipo_oxidado': 'equipo oxidado'
    }
    if not cls:
        return 'incidencia'
    key = str(cls).lower()
    return mapping.get(key, key.replace('_', ' '))

def _speech_summary_from_result(result: dict) -> str:
    if not result:
        return "No hay resultados de inspección disponibles."
    r = result.get("resumen_inspeccion", {}) or {}
    prio = r.get("prioridad_global") or "baja"
    urg  = r.get("urgencia_global") or "programada"
    zona = r.get("zona") or r.get("lugar") or "no especificada"
    total = r.get("detecciones") or result.get("analysis", {}).get("total_problems", 0)

    top_txt = ""
    if isinstance(result.get("reporte_incidencia"), list) and result["reporte_incidencia"]:
        t = result["reporte_incidencia"][0]
        conf = t.get("confianza")
        conf_txt = f"{conf:.1f} por ciento" if isinstance(conf, (int, float)) else str(conf)
        top_txt = f"Principal: {_friendly_name(t.get('problema'))} con confianza {conf_txt}. "

    pasos = []
    if isinstance(r.get("acciones_recomendadas_globales"), list):
        pasos = r["acciones_recomendadas_globales"][:3]
    pasos_txt = (". ".join(pasos) + ".") if pasos else "Revisa las acciones recomendadas en pantalla."

    return (
        f"Resumen de inspección. Se detectó un total de {total} problema o problemas. "
        f"Prioridad {prio}. Urgencia {urg}. Zona {zona}. {top_txt}{pasos_txt}"
    )

def _tts_id(text: str) -> str:
    if not text:
        return ""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

# ---- Frases de control de voz (acento-robusto) ----
def _accent_regex(s: str) -> str:
    """Convierte una frase base a un patrón regex que acepta acentos y espacios variables."""
    repl = {
        "a": "[aá]", "e": "[eé]", "i": "[ií]", "o": "[oó]", "u": "[uúü]",
        "á": "[aá]", "é": "[eé]", "í": "[ií]", "ó": "[oó]", "ú": "[uúü]", "ü": "[uúü]"
    }
    out = []
    for ch in s:
        if ch.isspace():
            out.append(r"\s+")
        else:
            out.append(repl.get(ch.lower(), re.escape(ch)))
    return "".join(out)

PHRASES_SILENCE_ON = [
    "solo texto", "sin voz", "no leer", "ya no hables", "ya pare",
    "no hables", "no hablar", "modo texto", "solo en texto",
    "texto nomas", "texto nada mas", "solo en texto", "solo responde en texto"
]
PHRASES_SILENCE_OFF = [
    "habla", "leer en voz", "activa voz", "vuelve a hablar",
    "puedes hablar", "con voz", "habla en voz"
]
SILENCE_ON_PATTERNS = [re.compile(r"\b" + _accent_regex(p) + r"\b", re.IGNORECASE) for p in PHRASES_SILENCE_ON]
SILENCE_OFF_PATTERNS = [re.compile(r"\b" + _accent_regex(p) + r"\b", re.IGNORECASE) for p in PHRASES_SILENCE_OFF]

def _match_any(patterns, text: str) -> bool:
    return any(p.search(text) for p in patterns)

def _strip_control_phrases(text: str) -> str:
    t = text
    for p in SILENCE_ON_PATTERNS + SILENCE_OFF_PATTERNS:
        t = p.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip()

# ---------- Limpieza/merge de parciales para ES ----------
_ws_re = re.compile(r"\s+")
_spaces_before_punct = re.compile(r"\s+([,.;:!?])")
_spaces_after_open = re.compile(r"([¿¡\(])\s+")
_spaces_before_close = re.compile(r"\s+([\)\]])")

def _normalize_es(text: str) -> str:
    """Limpieza ligera: espacios, signos y capitaliza al inicio de frase."""
    if not text:
        return ""
    t = text.strip()
    t = _ws_re.sub(" ", t)
    t = _spaces_before_punct.sub(r"\1", t)
    t = _spaces_after_open.sub(r"\1", t)
    t = _spaces_before_close.sub(r"\1", t)
    # Capitaliza primera letra si procede
    if t and t[0].isalpha():
        t = t[0].upper() + t[1:]
    return t

def _smart_merge(prev: str, new: str) -> str:
    """
    Une 'new' a 'prev' evitando duplicar palabras entre bordes.
    Busca la mayor coincidencia de 3–6 palabras al final de prev con el inicio de new.
    """
    prev = prev or ""
    new = new or ""
    if not prev:
        return new

    p_tokens = prev.split()
    n_tokens = new.split()
    max_win = min(6, len(p_tokens), len(n_tokens))
    overlap = 0

    for w in range(max_win, 2, -1):  # busca ventanas de 6..3
        if p_tokens[-w:] == n_tokens[:w]:
            overlap = w
            break

    if overlap > 0:
        merged_tokens = p_tokens + n_tokens[overlap:]
    else:
        merged_tokens = p_tokens + n_tokens

    merged = " ".join(merged_tokens)
    return merged

def _merge_and_normalize(chunks_map: dict) -> str:
    """Recibe {seq: texto} y devuelve el texto unificado y normalizado."""
    if not chunks_map:
        return ""
    merged = ""
    for k in sorted(chunks_map.keys()):
        merged = _smart_merge(merged, chunks_map[k])
    return _normalize_es(merged)

# ====== helpers de cache JSON ======
def load_cached_result(filename):
    """Lee el resultado de inspección cacheado como JSON en static/results/<filename>.json."""
    try:
        path = os.path.join(app.config['RESULT_FOLDER'], secure_filename(filename) + ".json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        app.logger.warning(f"No se pudo leer cache JSON: {e}")
    return None

# ========= Flask (HUB-friendly paths) =========
BASE_DIR = Path(__file__).resolve().parent

# Aseguramos que Flask use las carpetas de ESTA subapp, sin depender del CWD
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static")
)

# Rutas absolutas para uploads/results dentro de esta subapp
app.config['UPLOAD_FOLDER'] = str(BASE_DIR / 'static' / 'uploads')
app.config['RESULT_FOLDER'] = str(BASE_DIR / 'static' / 'results')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'webp'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULT_FOLDER'], exist_ok=True)

# ========= Detector YOLO =========
try:
    # Import relativo (paquete) y fallback absoluto (ejecución directa)
    try:
        from .detector_problemas import ProblemDetector  # type: ignore
    except Exception:
        from detector_problemas import ProblemDetector  # type: ignore
    try:
        detector = ProblemDetector()
        print("✅ Detector de problemas (YOLO) inicializado con éxito")
    except Exception as e:
        print(f"❌ Error al inicializar ProblemDetector: {str(e)}")
        detector = None
except ImportError as e:
    print(f"❌ No se pudo importar el módulo detector: {str(e)}")
    detector = None

# ========= Analizador LLM (opcional) =========
llm_analyze = None
if client is not None:
    try:
        try:
            from .ai.llm_detector import analyze_image_to_structured  # type: ignore
        except Exception:
            from ai.llm_detector import analyze_image_to_structured  # type: ignore
        llm_analyze = analyze_image_to_structured
        print("🧪 Analizador LLM disponible")
    except Exception as e:
        print(f"⚠️ No se pudo importar ai.llm_detector: {e}")
        llm_analyze = None

# ========= Resolución dinámica del modo =========
def resolve_mode():
    """
    Devuelve 'yolo' o 'llm' según:
      - Si DETECTOR_MODE == 'yolo': usa YOLO si existe; si no, fallback a LLM si disponible.
      - Si DETECTOR_MODE == 'llm': usa LLM; si no existe, será error.
      - Si DETECTOR_MODE == 'auto': usa YOLO si existe; si no, LLM si existe; si ninguno, error.
    """
    mode = DETECTOR_MODE
    if mode == "yolo":
        if detector is not None:
            return "yolo"
        return "llm" if (client is not None and llm_analyze is not None) else "error"
    if mode == "llm":
        return "llm" if (client is not None and llm_analyze is not None) else "error"
    # auto (o cualquier otro valor inesperado)
    if detector is not None:
        return "yolo"
    if client is not None and llm_analyze is not None:
        return "llm"
    return "error"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    mode = resolve_mode()
    if mode == "error":
        msg = "No hay detector YOLO ni analizador LLM disponibles. Verifique dependencias/OPENAI_API_KEY."
        return render_template('error.html', message=msg)
    if mode == "yolo" and detector is None:
        return render_template('error.html', message="El sistema de detección (YOLO) no está disponible.")
    if mode == "llm" and (client is None or llm_analyze is None):
        return render_template('error.html', message="OPENAI_API_KEY o analizador LLM no configurados.")
    return render_template('problemas.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    global last_result
    mode = resolve_mode()
    if mode == "error":
        return jsonify({'error': 'No hay detector disponible (YOLO/LLM)'}), 503
    if 'file' not in request.files:
        return jsonify({'error': 'No se encontró archivo en la solicitud'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Tipo de archivo no permitido'}), 400

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = secure_filename(f"{timestamp}_{unique_id}_{file.filename}")
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        file.save(upload_path)
        if not os.path.exists(upload_path):
            return jsonify({'error': 'Error al guardar el archivo'}), 500

        zona = request.form.get('zona', '')
        if mode == "llm":
            try:
                result = llm_analyze(
                    client=client,
                    model=OPENAI_CHAT_MODEL,
                    image_path=upload_path,
                    zona=zona,
                    results_dir=app.config['RESULT_FOLDER']
                )
            except Exception as e:
                app.logger.error(f"Error LLM al analizar imagen: {e}")
                return jsonify({'error': 'Error interno del analizador LLM'}), 500
        else:
            # yolo
            result = detector.detect_problems(upload_path, zona=zona)
        if not result or 'error' in result:
            return jsonify({'error': result.get('error', 'Error desconocido al procesar la imagen')}), 500

        result.update({'timestamp': timestamp, 'filename': filename, 'status': 'success'})

        # Texto e ID para TTS
        try:
            result["summary_tts_text"] = _speech_summary_from_result(result)
            result["summary_tts_id"] = _tts_id(result["summary_tts_text"])
        except Exception:
            result["summary_tts_text"] = None
            result["summary_tts_id"] = ""

        # Cache JSON para chat/contexto
        try:
            json_path = os.path.join(app.config['RESULT_FOLDER'], f"{filename}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
        except Exception as e:
            app.logger.warning(f"No se pudo cachear JSON en /upload: {e}")

        last_result = result
        results_by_filename[filename] = result
        chat_progress.pop(filename, None)

        return jsonify(result)

    except Exception as e:
        app.logger.error(f"Error al procesar archivo: {str(e)}")
        return jsonify({'error': f"Error interno del servidor: {str(e)}"}), 500

@app.route('/history', methods=['GET'])
def get_history():
    try:
        processed_files = []
        for filename in sorted(os.listdir(app.config['UPLOAD_FOLDER']), reverse=True):
            if filename.lower().endswith(tuple(app.config['ALLOWED_EXTENSIONS'])):
                original = os.path.join(app.config['UPLOAD_FOLDER'], filename).replace('\\', '/')
                processed = os.path.join(app.config['RESULT_FOLDER'], filename).replace('\\', '/')
                if os.path.exists(processed):
                    processed_files.append({
                        'original': original,
                        'processed': processed,
                        'filename': filename,
                        'timestamp': ' '.join(filename.split('_')[0:2])
                    })
        return jsonify({'history': processed_files[:10]})
    except Exception as e:
        app.logger.error(f"Error al obtener historial: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/inspect/<filename>', methods=['GET'])
def inspect_file(filename):
    global last_result
    mode = resolve_mode()
    if mode == "error":
        return jsonify({'error': 'No hay detector disponible (YOLO/LLM)'}), 503
    if not allowed_file(filename):
        return jsonify({'error': 'Tipo de archivo no permitido'}), 400
    try:
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        result_path = os.path.join(app.config['RESULT_FOLDER'], secure_filename(filename))
        if not os.path.exists(upload_path) or not os.path.exists(result_path):
            return jsonify({'error': 'Archivo no encontrado'}), 404

        zona = request.args.get('zona', '')
        if mode == "llm":
            if client is None or llm_analyze is None:
                return jsonify({'error': 'OPENAI_API_KEY o analizador LLM no configurados'}), 503
            try:
                result = llm_analyze(
                    client=client,
                    model=OPENAI_CHAT_MODEL,
                    image_path=upload_path,
                    zona=zona,
                    results_dir=app.config['RESULT_FOLDER']
                )
            except Exception as e:
                app.logger.error(f"Error LLM al analizar imagen: {e}")
                return jsonify({'error': 'Error interno del analizador LLM'}), 500
        else:
            result = detector.detect_problems(upload_path, zona=zona)
        if not result or 'error' in result:
            return jsonify({'error': result.get('error', 'Error al procesar la imagen')}), 500

        # Texto e ID para TTS
        try:
            result["summary_tts_text"] = _speech_summary_from_result(result)
            result["summary_tts_id"] = _tts_id(result["summary_tts_text"])
        except Exception:
            result["summary_tts_text"] = None
            result["summary_tts_id"] = ""

        # Cache JSON también aquí
        try:
            json_path = os.path.join(app.config['RESULT_FOLDER'], f"{filename}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
        except Exception as e:
            app.logger.warning(f"No se pudo cachear JSON en /inspect: {e}")

        last_result = result
        results_by_filename[filename] = result
        chat_progress.pop(filename, None)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error al inspeccionar archivo: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ========= Chat SOLO OpenAI =========
@app.route('/ask', methods=['POST'])
def ask():
    """
    Body:
    {
      "q": "pregunta",
      "filename": "opcional",
      "mode": "initial" | "chat",
      "speak": true|false   # opcional; si no viene se usa estado persistente SPEECH_ENABLED
    }
    Retorna:
    { "answer": "...", "tts_text": "...", "used_model": "...", "has_context": true|false }
    """
    global last_result, SPEECH_ENABLED
    if client is None:
        return jsonify({"error": "OPENAI_API_KEY no configurada en el servidor."}), 500

    payload = request.get_json(silent=True) or {}
    raw_question = (payload.get("q") or "").strip()
    filename = payload.get("filename")
    mode = (payload.get("mode") or "chat").lower()

    if not raw_question:
        return jsonify({"error": "Falta el texto de la pregunta (q)."}), 400

    # Control de voz por frases (acento-robusto)
    q_for_match = raw_question
    if _match_any(SILENCE_ON_PATTERNS, q_for_match):
        SPEECH_ENABLED = False
    elif _match_any(SILENCE_OFF_PATTERNS, q_for_match):
        SPEECH_ENABLED = True

    # Determinar si leer esta respuesta (param > persistente)
    if "speak" in payload:
        speak = bool(payload.get("speak"))
        SPEECH_ENABLED = speak  # sincroniza estado persistente con override explícito
    else:
        speak = SPEECH_ENABLED

    # Limpiar frases de control del prompt enviado al modelo
    question = _strip_control_phrases(raw_question)

    # ====== Contexto desde cache JSON por filename (si existe) o last_result / o volver a correr
    ctx_result = last_result
    if filename:
        if not allowed_file(filename):
            return jsonify({'error': 'Tipo de archivo no permitido'}), 400

        # 1) Intentar primero leer el resultado cacheado en JSON
        cached = load_cached_result(filename)
        if cached:
            ctx_result = cached
        else:
            # 2) Si en memoria lo tenemos por nombre, úsalo
            if filename in results_by_filename:
                ctx_result = results_by_filename.get(filename)
            else:
                # 3) Fallback: volver a correr el detector si existe el archivo
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
                if os.path.exists(upload_path):
                    try:
                        mode_now = resolve_mode()
                        if mode_now == "llm" and llm_analyze is not None:
                            ctx_result = llm_analyze(
                                client=client,
                                model=OPENAI_CHAT_MODEL,
                                image_path=upload_path,
                                zona="",
                                results_dir=app.config['RESULT_FOLDER']
                            )
                        elif mode_now == "yolo" and detector is not None:
                            ctx_result = detector.detect_problems(upload_path)
                    except Exception as e:
                        app.logger.error(f"Error creando contexto para chatbot: {str(e)}")

    compact_ctx = _compact_result_for_llm(ctx_result) if ctx_result else {}

    # Prompts
    base_system = (
        "Eres un asistente técnico de mantenimiento de infraestructura. "
        "Responde SIEMPRE en español, con tono profesional, claro y accionable. "
        "No inventes datos fuera del contexto; si falta info, dilo y sugiere cómo obtenerla."
    )
    style_initial = (
        "Si hay contexto de inspección, entrega: (1) resumen breve (1–2 líneas), "
        "(2) prioridad/urgencia, (3) 3 pasos recomendados y EPP si hay riesgo, "
        "(4) profesional sugerido y tiempo (SLA)."
    )
    style_chat = (
        "Modo chat: responde SOLO a la pregunta del usuario en 1–4 frases. "
        "NO repitas el reporte, prioridad, urgencia ni SLA salvo que el usuario lo pida. "
        "Evita listas largas y encabezados, a menos que el usuario diga 'paso a paso'."
    )
    style_prompt = style_initial if mode == "initial" else style_chat

    # Si solo vinieron frases de control y quedó vacío, devuelve confirmación
    if not question:
        msg = "De acuerdo, responderé solo en texto a partir de ahora." if not SPEECH_ENABLED \
              else "Listo, activaré la lectura en voz a partir de ahora."
        return jsonify({
            "answer": msg,
            "used_model": OPENAI_MODEL,
            "has_context": bool(compact_ctx),
            "tts_text": (msg if SPEECH_ENABLED else None)
        })

    try:
        messages = [
            {"role": "system", "content": base_system},
            {"role": "system", "content": style_prompt},
            # Reglas adicionales de coherencia (de tu local)
            {"role": "system", "content": (
                "Reglas de coherencia: 1) considera TODAS las incidencias del contexto (no solo una), "
                "2) si el usuario pide acciones o 'que hago', sugiere pasos para cada incidencia detectada "
                "empezando por la de mayor prioridad, 3) si hay conflictos (ej. agua cerca de equipo electrico), "
                "advierte y prioriza seguridad/EPP."
            )},
            {
                "role": "user",
                "content": (
                    "Pregunta del usuario:\n" + question +
                    "\n\nContexto de inspección (JSON compactado, si existe):\n" +
                    json.dumps(compact_ctx, ensure_ascii=False)
                )
            }
        ]
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,  # = OPENAI_CHAT_MODEL (retrocompat)
            messages=messages,
            temperature=0.3,
            max_tokens=400 if mode == "initial" else 200
        )
        text = resp.choices[0].message.content.strip() if resp and resp.choices else "No pude generar respuesta."

        out = {
            "answer": text,
            "used_model": OPENAI_MODEL,
            "has_context": bool(compact_ctx)
        }
        if speak:
            out["tts_text"] = text
        return jsonify(out)
    except Exception as e:
        app.logger.error(f"OpenAI error: {e}")
        return jsonify({"error": f"Error consultando OpenAI: {str(e)}"}), 500

# ========= TTS =========
@app.post("/tts")
def tts():
    """
    Body JSON: { "text": "texto a leer", "voice": "alloy" }
    Devuelve: audio/mpeg
    """
    if client is None:
        return jsonify({"error": "OPENAI_API_KEY no configurada"}), 500

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    voice = data.get("voice") or "alloy"

    if not text:
        return jsonify({"error": "Falta 'text' en el body"}), 400

    try:
        with client.audio.speech.with_streaming_response.create(
            model=OPENAI_TTS_MODEL,
            voice=voice,
            input=text
        ) as speech:
            audio_bytes = io.BytesIO(speech.read())
            audio_bytes.seek(0)
            return send_file(
                audio_bytes,
                mimetype="audio/mpeg",
                as_attachment=False,
                download_name="voz.mp3"
            )
    except Exception as e:
        app.logger.error(f"TTS error: {e}")
        return jsonify({"error": f"Error TTS: {str(e)}"}), 500

# ========= STT =========
@app.post("/stt")
def stt():
    """
    Form-data: audio: <archivo> (webm/mp3/wav/ogg)
              [sid: <string opcional>]  # si llega, se limpia el buffer de esa sesión
    Retorna: { "text": "transcripción", "sid": "<echo si llegó>" }
    """
    if client is None:
        return jsonify({"error": "OPENAI_API_KEY no configurada"}), 500

    if "audio" not in request.files:
        return jsonify({"error": "Falta campo 'audio' en form-data"}), 400

    fs = request.files["audio"]
    if fs.filename == "":
        return jsonify({"error": "Archivo vacío"}), 400

    sid = (request.form.get("sid") or "").strip() or None

    try:
        raw = fs.read()
        if not raw or len(raw) < 800:
            return jsonify({"text": "", "sid": sid})

        bio = io.BytesIO(raw)
        bio.name = fs.filename or "audio.webm"
        bio.seek(0)

        try:
            tr = client.audio.transcriptions.create(
                model=OPENAI_STT_MODEL,
                file=bio,
                language="es"
            )
        except Exception:
            bio.seek(0)
            tr = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=bio,
                language="es"
            )

        if sid and sid in LIVE_TRANSCRIPTS:
            try:
                LIVE_TRANSCRIPTS.pop(sid, None)
            except Exception:
                pass

        return jsonify({"text": getattr(tr, "text", "") or "", "sid": sid})
    except Exception as e:
        app.logger.error(f"STT error: {e}")
        return jsonify({"text": "", "sid": sid})

# ========= STT en “tiempo (casi) real” por chunks =========
@app.post("/stt_chunk")
def stt_chunk():
    """
    Form-data:
      audio: <blob> (webm/mp3/wav/ogg)
      seq: <int>
      sid: <string opcional>  # Identificador de sesión para devolver texto 'merged'
    Respuesta: { "partial": "<texto>", "seq": <int|None>, "merged": "<texto_unificado_opcional>", "sid": "<eco>" }
    """
    if client is None:
        return jsonify({"error": "OPENAI_API_KEY no configurada"}), 500

    if "audio" not in request.files:
        return jsonify({"error": "Falta campo 'audio' en form-data"}), 400

    fs = request.files["audio"]
    if fs.filename == "":
        return jsonify({"error": "Archivo vacío"}), 400

    seq_raw = request.form.get("seq")
    seq = int(seq_raw) if seq_raw and seq_raw.isdigit() else None
    sid = (request.form.get("sid") or "").strip() or None

    try:
        raw = fs.read()
        if not raw or len(raw) < 800:
            merged = ""
            if sid and sid in LIVE_TRANSCRIPTS:
                merged = _merge_and_normalize(LIVE_TRANSCRIPTS.get(sid, {}))
            return jsonify({"partial": "", "seq": seq, "merged": merged, "sid": sid})

        bio = io.BytesIO(raw)
        bio.name = fs.filename or "chunk.webm"
        bio.seek(0)

        try:
            tr = client.audio.transcriptions.create(
                model=OPENAI_STT_MODEL,
                file=bio,
                language="es"
            )
        except Exception as e1:
            app.logger.warning(f"STT con {OPENAI_STT_MODEL} falló, fallback: {e1}")
            bio.seek(0)
            tr = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=bio,
                language="es"
            )

        partial = getattr(tr, "text", "") or ""

        merged = None
        if sid:
            bucket = LIVE_TRANSCRIPTS.setdefault(sid, {})
            if seq is not None:
                bucket[seq] = partial
            else:
                next_idx = max(bucket.keys(), default=-1) + 1
                bucket[next_idx] = partial
            merged = _merge_and_normalize(bucket)

        payload = {"partial": partial, "seq": seq, "sid": sid}
        if merged is not None:
            payload["merged"] = merged
        return jsonify(payload)

    except Exception as e:
        app.logger.error(f"STT chunk error: {e}")
        merged = ""
        if sid and sid in LIVE_TRANSCRIPTS:
            merged = _merge_and_normalize(LIVE_TRANSCRIPTS.get(sid, {}))
        return jsonify({"partial": "", "seq": seq, "merged": merged, "sid": sid})

# ====== Cierre explícito de sesión STT (opcional) ======
@app.post("/stt_close")
def stt_close():
    """
    JSON: { "sid": "<id de sesión>" }
    Efecto: borra el buffer LIVE_TRANSCRIPTS[sid] para liberar memoria/evitar parciales tardíos.
    """
    data = request.get_json(silent=True) or {}
    sid = (data.get("sid") or "").strip()
    if not sid:
        return jsonify({"ok": False, "error": "Falta 'sid'"}), 400
    try:
        LIVE_TRANSCRIPTS.pop(sid, None)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ====== ENDPOINT DE SALUD ======
@app.route("/healthz", methods=["GET"])
def healthz():
    return {"ok": True}

# Alias para que el HUB pueda importarlo como WSGI app:
flask_app = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
