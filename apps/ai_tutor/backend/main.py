from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import uuid
from pathlib import Path

# ✅ Imports correctos: este archivo vive en apps/ai_tutor/backend/
# Antes: .backend.agents...  (eso rompía en Render)
try:
    from .agents.tutor_agent import TutorAgent
    from .utils.voice_processor import VoiceProcessor
except Exception:
    # Fallback por si se ejecuta como módulo suelto
    from agents.tutor_agent import TutorAgent
    from utils.voice_processor import VoiceProcessor

app = FastAPI(title="Tutor AI Futurista")

# ── Base absoluta de ESTA subapp (sirve si este archivo está en apps/ai_tutor/ o apps/ai_tutor/backend/) ──
FILE_DIR = Path(__file__).resolve().parent
# Si este main.py está dentro de apps/ai_tutor/backend/, STATIC está un nivel arriba
if (FILE_DIR / "static").exists() and (FILE_DIR / "templates").exists():
    BASE = FILE_DIR
else:
    BASE = FILE_DIR.parent  # normalmente apps/ai_tutor/

# Estáticos / plantillas propios de la subapp (se verán como /ai-tutor/static/... al montarla)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

# Asegurar carpeta de audio dentro de static
os.makedirs(BASE / "static" / "audio", exist_ok=True)

tutor = TutorAgent()
voice_processor = VoiceProcessor()

# WebSocket para comunicación en tiempo real
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()

            if data["type"] == "text":
                response = tutor.generate_response(data["content"])
                await websocket.send_json({
                    "type": "text",
                    "content": response
                })

                # Convertir a voz
                audio_fs_path = voice_processor.text_to_speech(response)

                # Normalizar a URL servible por StaticFiles (/ai-tutor/static/...)
                try:
                    static_root = (BASE / "static").resolve()
                    rel = Path(audio_fs_path).resolve().relative_to(static_root)
                    audio_url = f"/static/{rel.as_posix()}"
                except Exception:
                    # Si ya viene como "static/..." o URL, lo dejamos tal cual
                    audio_url = audio_fs_path

                await websocket.send_json({
                    "type": "audio",
                    "path": audio_url
                })

            elif data["type"] == "audio":
                # data["path"] debería ser accesible por el VoiceProcessor (según tu implementación)
                text = voice_processor.speech_to_text(data["path"])
                response = tutor.generate_response(text)
                await websocket.send_json({
                    "type": "text",
                    "content": response
                })

    except Exception as e:
        print(f"Error: {e}")

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
