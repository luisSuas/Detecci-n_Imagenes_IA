# app.py (HUB)
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.middleware.wsgi import WSGIMiddleware

# Flask (AI Detect v1)
from apps.ai_detect.app import flask_app as detect_flask_app

# Flask (AI Detect v2)  ⬅️ NUEVO
from apps.ai_detectV2.backend import app as detect_v2_flask_app

# FastAPI (AI Tutor y AI Seguridad)
from apps.ai_tutor.backend.main import app as tutor_app
from apps.ai_seguridad.main import app as seguridad_app

hub = FastAPI(title="Ángel · AI Hub")

# Montajes
hub.mount("/ai-detect", WSGIMiddleware(detect_flask_app))
hub.mount("/ai-detect-v2", WSGIMiddleware(detect_v2_flask_app))  # ⬅️ NUEVO
hub.mount("/ai-tutor", tutor_app)
hub.mount("/ai-seguridad", seguridad_app)


@hub.get("/", response_class=HTMLResponse)
def index():
    return """
    <h2>Ángel · HUB de IA</h2>
    <ul>
      <li><a href="/ai-detect">AI Detect v1 · UI</a> · <a href="/ai-detect/healthz">health</a></li>
      <li><a href="/ai-detect-v2">AI Detect v2 · UI</a></li>
      <li><a href="/ai-tutor">AI Tutor · UI</a> · <a href="/ai-tutor/docs">docs</a></li>
      <li><a href="/ai-seguridad">AI Seguridad · UI</a> · <a href="/ai-seguridad/docs">docs</a></li>
    </ul>
    """

# Entry point para Gunicorn/Uvicorn
app = hub
