from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
from pathlib import Path

# Imports relativos robustos
try:
    from .agents.tutor_agent import TutorAgent
    from .utils.voice_processor import VoiceProcessor
except Exception:
    from agents.tutor_agent import TutorAgent
    from utils.voice_processor import VoiceProcessor

app = FastAPI(title="Tutor AI Futurista")

# ── Resolución de rutas (soporta main.py en ai_tutor/ o ai_tutor/backend/) ──
FILE_DIR = Path(__file__).resolve().parent
BASE = FILE_DIR if (FILE_DIR / "static").exists() and (FILE_DIR / "templates").exists() else FILE_DIR.parent

# ✅ PATH y NOMBRE ÚNICOS para esta sub-app (coinciden con el usado en url_for)
#    En producción, si esta app está montada en /ai-tutor, los assets quedarán en /ai-tutor/ai-tutor-static/...
app.mount("/ai-tutor-static", StaticFiles(directory=str(BASE / "static")), name="ai_tutor_static")

templates = Jinja2Templates(directory=str(BASE / "templates"))

# Asegurar carpeta de audio
os.makedirs(BASE / "static" / "audio", exist_ok=True)

tutor = TutorAgent()
voice_processor = VoiceProcessor()

# Healthcheck para Render
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

# Página principal
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# WebSocket de chat/voz
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "text":
                user_text = data.get("content", "")
                response = tutor.generate_response(user_text)

                # 1) responder texto
                await websocket.send_json({"type": "text", "content": response})

                # 2) sintetizar y mandar URL de audio servible
                audio_fs_path = voice_processor.text_to_speech(response)

                # Respetar root_path cuando esta sub-app está bajo prefijo (/ai-tutor)
                root = websocket.scope.get("root_path", "") or ""
                try:
                    static_root = (BASE / "static").resolve()
                    rel = Path(audio_fs_path).resolve().relative_to(static_root)
                    # Usa el MISMO prefijo público del mount de arriba
                    audio_url = f"{root}/ai-tutor-static/{rel.as_posix()}"
                except Exception:
                    p = str(audio_fs_path).replace("\\", "/")
                    if p.startswith("/ai-tutor-static/"):
                        audio_url = f"{root}{p}"
                    elif p.startswith("ai-tutor-static/"):
                        audio_url = f"{root}/{p}"
                    else:
                        audio_url = p  # último recurso

                await websocket.send_json({"type": "audio", "path": audio_url})

            elif msg_type == "audio":
                audio_path = data.get("path", "")
                text = voice_processor.speech_to_text(audio_path)
                response = tutor.generate_response(text)
                await websocket.send_json({"type": "text", "content": response})

            else:
                # Ignorar tipos desconocidos
                pass

    except Exception as e:
        print(f"[WS] error: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
