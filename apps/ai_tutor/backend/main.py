from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
from pathlib import Path

# Imports relativos robustos (funciona dentro y fuera del paquete)
try:
    from .agents.tutor_agent import TutorAgent
    from .utils.voice_processor import VoiceProcessor
except Exception:  # ejecución directa
    from agents.tutor_agent import TutorAgent
    from utils.voice_processor import VoiceProcessor

app = FastAPI(title="Tutor AI Futurista")

# ── Resolución de rutas (soporta main.py en ai_tutor/ o ai_tutor/backend/) ──
FILE_DIR = Path(__file__).resolve().parent
if (FILE_DIR / "static").exists() and (FILE_DIR / "templates").exists():
    BASE = FILE_DIR
else:
    BASE = FILE_DIR.parent  # normalmente ai_tutor/

# Estáticos / plantillas de la subapp
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

# Asegurar carpeta de audio
os.makedirs(BASE / "static" / "audio", exist_ok=True)

tutor = TutorAgent()
voice_processor = VoiceProcessor()

# Healthcheck simple para Render
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

                # 2) sintetizar y mandar URL de audio sirvible
                audio_fs_path = voice_processor.text_to_speech(response)

                # Construir URL respetando root_path (p. ej. /ai-tutor)
                root = websocket.scope.get("root_path", "") or ""
                try:
                    static_root = (BASE / "static").resolve()
                    rel = Path(audio_fs_path).resolve().relative_to(static_root)
                    audio_url = f"{root}/static/{rel.as_posix()}"
                except Exception:
                    # Si ya es una ruta relativa dentro de static o URL absoluta
                    p = str(audio_fs_path).replace("\\", "/")
                    if p.startswith("/static/"):
                        audio_url = f"{root}{p}"
                    elif p.startswith("static/"):
                        audio_url = f"{root}/{p}"
                    else:
                        audio_url = p  # último recurso

                await websocket.send_json({"type": "audio", "path": audio_url})

            elif msg_type == "audio":
                # Según tu implementación de VoiceProcessor, `data["path"]` puede ser
                # una URL/archivo accesible por el servidor para STT.
                audio_path = data.get("path", "")
                text = voice_processor.speech_to_text(audio_path)
                response = tutor.generate_response(text)

                await websocket.send_json({"type": "text", "content": response})

            else:
                # Mensajes no reconocidos: ignorar o loguear
                pass

    except Exception as e:
        # Log mínimo; revisa logs de Render si algo va mal
        print(f"[WS] error: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
