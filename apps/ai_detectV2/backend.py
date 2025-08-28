# backend.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
import os
import base64
import tempfile
import speech_recognition as sr
from PIL import Image
import json
import re
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_DIR   = BASE_DIR / "static"
UPLOAD_DIR   = BASE_DIR / "temp_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=None)
CORS(app)

# OpenAI client (API v1.x)
# Asegúrate de exportar OPENAI_API_KEY en tu entorno
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Opcional: limita tamaño de subida (ej. 20 MB)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


# ─────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────
def _json_from_text(text: str):
    """
    Intenta extraer un JSON de un texto del modelo.
    Soporta que venga dentro de ```json ... ```, o mezclado con explicación.
    """
    if not text:
        return None

    # 1) bloque ```json ... ```
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # 2) primer {...} que parezca JSON
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass

    return None


def extract_objects_from_analysis(analysis_text: str):
    """
    Heurística simple para contar menciones de objetos en texto libre.
    Ajusta la lista si te interesa otro dominio.
    """
    objects = {}
    common_objects = [
        "persona", "coche", "árbol", "mesa", "silla", "ventana",
        "puerta", "edificio", "computadora", "teléfono", "libro",
        "planta", "cama", "lámpara", "bicicleta", "perro", "gato",
        "flor", "nube", "sol", "montaña", "río", "mar", "cuchara",
        "tenedor", "vaso", "plato", "sofá", "televisor", "monitor",
        "auto", "motocicleta", "bus", "camión", "avión", "barco"
    ]
    tl = (analysis_text or "").lower()
    for obj in common_objects:
        cnt = tl.count(obj)
        if cnt > 0:
            objects[obj] = cnt
    return objects


# ─────────────────────────────────────────────────────────────
# Rutas de estáticos / frontend
# ─────────────────────────────────────────────────────────────
@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/")
def index():
    # Sirve la página principal
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.get("/static/<path:filename>")
def static_files(filename):
    # Sirve /static/... desde la carpeta static
    return send_from_directory(STATIC_DIR, filename)

@app.get("/frontend/<path:filename>")
def frontend_files(filename):
    # Si tu index importa algo desde /frontend/...
    return send_from_directory(FRONTEND_DIR, filename)


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────
@app.post("/upload")
def upload_file():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No se proporcionó ningún archivo"}), 400

        file = request.files["file"]
        if not file or file.filename == "":
            return jsonify({"error": "Nombre de archivo vacío"}), 400

        tmp_path = UPLOAD_DIR / file.filename
        file.save(tmp_path)

        # <<< NUEVO: idioma desde query (?lang=es|en)
        lang = (request.args.get("lang") or "es").lower()
        if lang not in ("es", "en"):
            lang = "es"

        result = process_image(tmp_path, lang=lang)   # <<< pasa lang

        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def process_image(image_path: Path, lang: str = "es"):
    Image.open(image_path).close()

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    # <<< NUEVO: prompt por idioma
    if lang == "en":
        prompt = (
            "Analyze this image and list every visible object with counts. "
            "Return a helpful scene analysis and practical suggestions based on what you see. "
            "Answer in English. Return JSON as: "
            "{objects: [{name: string, count: number}], analysis: string, suggestions: string}"
        )
    else:  # es
        prompt = (
            "Analiza esta imagen y detalla todos los objetos visibles. "
            "Proporciona una lista cuantificada de cada objeto encontrado, un análisis "
            "detallado de la escena y sugerencias prácticas basadas en lo que observas. "
            "Responde en español. Devuélvelo en formato JSON con: "
            "{objects: [{name: string, count: number}], analysis: string, suggestions: string}"
        )

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ],
        }],
        max_tokens=1000,
    )

    text = resp.choices[0].message.content

    # Intentamos extraer JSON estructurado
    data = _json_from_text(text)
    if data:
        objects_detected = {}
        for obj in data.get("objects", []):
            name = obj.get("name")
            count = obj.get("count")
            if name:
                objects_detected[name] = int(count) if isinstance(count, (int, float)) else 1

        analysis_text = (data.get("analysis") or "").strip()
        suggestions   = (data.get("suggestions") or "").strip()
        full_analysis = analysis_text + ("\n\nSugerencias:\n" + suggestions if suggestions else "")

        return {"analysis": full_analysis, "objects_detected": objects_detected}

    # Fallback si el modelo no devolvió JSON válido
    return {
        "analysis": text,
        "objects_detected": extract_objects_from_analysis(text),
    }


@app.post("/speech-to-text")
def speech_to_text():
    try:
        if "audio" not in request.files:
            return jsonify({"error": "No se proporcionó audio"}), 400

        audio_file = request.files["audio"]
        tmp_path = UPLOAD_DIR / "audio_input.wav"
        audio_file.save(tmp_path)

        recognizer = sr.Recognizer()
        with sr.AudioFile(str(tmp_path)) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="es-ES")

        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/chat")
def chat():
    try:
        data = request.get_json(silent=True) or {}
        user_message = (data.get("message") or "").strip()
        if not user_message:
            return jsonify({"error": "Mensaje vacío"}), 400

        lang = (request.args.get("lang") or "es").lower()
        if lang not in ("es", "en"):
            lang = "es"

        system_msg = (
            "Eres un asistente útil con un estilo futurista. Responde siempre en español."
            if lang == "es" else
            "You are a helpful assistant with a futuristic style. Always respond in English."
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_message},
            ],
            max_tokens=600,
            temperature=0.7,
        )

        bot_response = resp.choices[0].message.content
        return jsonify({"response": bot_response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Sirve assets del frontend directamente en la raíz de la app montada
@app.get("/styles.css")
def styles_root():
    return send_from_directory(FRONTEND_DIR, "styles.css")

@app.get("/script.js")
def script_root():
    return send_from_directory(FRONTEND_DIR, "script.js")

@app.get("/logo-black.svg")
def logo_root():
    return send_from_directory(FRONTEND_DIR, "logo-black.svg")

# Opcional: si tu index usa otros archivos en FRONTEND_DIR, expónlos genéricamente
@app.get("/assets/<path:filename>")
def front_assets(filename):
    return send_from_directory(FRONTEND_DIR, filename)


# ─────────────────────────────────────────────────────────────
# Dev server
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Para local: http://127.0.0.1:5000/
    app.run(host="0.0.0.0", port=5000, debug=True)
