import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Request, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from ultralytics import YOLO
import asyncio
import uuid
import os
import base64
from pathlib import Path
import json
from typing import Dict
import threading
import time

app = FastAPI(
    title="Sistema de Seguridad",
    description="Detección de objetos peligrosos en tiempo real"
)

# ───────────────────────── Directorios (robusto para prod y subpath) ─────────────────────────
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Crear directorios necesarios
os.makedirs(STATIC_DIR / "css", exist_ok=True)
os.makedirs(STATIC_DIR / "js", exist_ok=True)
os.makedirs(STATIC_DIR / "uploads", exist_ok=True)

# ───────────────────────── Carga perezosa del modelo ─────────────────────────
MODEL_PATH = BASE_DIR / "yolov8n.pt"
_model = None
_model_lock = threading.Lock()

def get_model() -> YOLO:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                # Si no existe el archivo, YOLO intentará resolverlo por nombre (siempre que esté disponible)
                model_source = str(MODEL_PATH) if MODEL_PATH.exists() else "yolov8n.pt"
                _model = YOLO(model_source)  # CPU por defecto si no hay GPU
    return _model

# Clases consideradas peligrosas (personalizable)
DANGER_CLASSES = {'knife', 'gun', 'pistol', 'weapon', 'firearm', 'rifle'}
SAFETY_CLASSES = {'person', 'backpack', 'handbag', 'suitcase', 'cell phone'}

# ───────────────────────── Detección ─────────────────────────
def detect_dangers(frame):
    """
    Devuelve:
      processed_frame, danger_detected(bool), detected_objects(list)
    """
    model = get_model()
    results = model(frame, verbose=False)
    danger_detected = False
    detected_objects = []

    # Dibujos sobre 'frame' en sitio
    for result in results:
        for box in result.boxes:
            class_id = int(box.cls)
            class_name = model.names.get(class_id, str(class_id))
            confidence = float(box.conf)

            x1, y1, x2, y2 = map(int, box.xyxy[0])

            if class_name in DANGER_CLASSES and confidence > 0.5:
                danger_detected = True
                # Rojo para peligros
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                label = f"ALERTA! {class_name.upper()} {confidence:.2f}"
                cv2.putText(frame, label, (x1, max(20, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                detected_objects.append({
                    "class": class_name,
                    "confidence": confidence,
                    "position": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                })

            elif class_name in SAFETY_CLASSES and confidence > 0.5:
                # Verde para elementos “seguros”
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{class_name.upper()} {confidence:.2f}"
                cv2.putText(frame, label, (x1, max(20, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # Banner superior si hay alerta
    if danger_detected:
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 50), (0, 0, 255), -1)
        cv2.putText(frame, "ZONA PELIGROSA DETECTADA!", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    return frame, danger_detected, detected_objects

# ───────────────────────── Home ─────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ───────────────────────── Upload de Imagen ─────────────────────────
@app.post("/upload/image")
async def upload_image(request: Request, file: UploadFile = File(...)):
    raw = await file.read()
    nparr = np.frombuffer(raw, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        return {"error": "El archivo no es una imagen válida."}

    processed_frame, danger_detected, detected_objects = detect_dangers(frame)

    # Guardar imagen procesada
    out_name = f"processed_{uuid.uuid4().hex}.jpg"
    out_path = STATIC_DIR / "uploads" / out_name
    cv2.imwrite(str(out_path), processed_frame)

    # Imagen en base64 para previsualización inmediata
    ok, img_encoded = cv2.imencode(".jpg", processed_frame)
    if not ok:
        return {"error": "No se pudo codificar la imagen de salida."}
    img_base64 = base64.b64encode(img_encoded).decode("utf-8")

    # URL estática consciente de root_path
    root = request.scope.get("root_path", "") or ""
    image_url = f"{root}/static/uploads/{out_name}"

    return {
        "danger_detected": danger_detected,
        "detected_objects": detected_objects,
        "image_base64": img_base64,
        "image_url": image_url
    }

# ───────────────────────── Upload de Video ─────────────────────────
@app.post("/upload/video")
async def upload_video(request: Request, file: UploadFile = File(...)):
    # Guardar temporal
    temp_name = f"temp_{uuid.uuid4().hex}.mp4"
    temp_file = STATIC_DIR / "uploads" / temp_name
    with open(temp_file, "wb") as buffer:
        buffer.write(await file.read())

    cap = cv2.VideoCapture(str(temp_file))
    if not cap.isOpened():
        try:
            os.remove(temp_file)
        except Exception:
            pass
        return {"error": "No se pudo abrir el video."}

    # Configurar video de salida
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 1:
        fps = 24.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

    out_name = f"output_{uuid.uuid4().hex}.mp4"
    out_file = STATIC_DIR / "uploads" / out_name
    out = cv2.VideoWriter(str(out_file), fourcc, fps, (width, height))

    alert_in_video = False
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            processed_frame, danger_detected, _ = detect_dangers(frame)
            if danger_detected:
                alert_in_video = True
            out.write(processed_frame)
    finally:
        cap.release()
        out.release()
        try:
            os.remove(temp_file)
        except Exception:
            pass

    root = request.scope.get("root_path", "") or ""
    return {
        "alert": alert_in_video,
        "processed_video": f"{root}/static/uploads/{out_name}"
    }

# ───────────────────────── Live / WebSocket ─────────────────────────
active_cameras: Dict[int, cv2.VideoCapture] = {}
camera_lock = threading.Lock()

# Cooldown para no spamear alertas por WS (segundos)
ALERT_COOLDOWN_SEC = 5
_last_alert_sent: Dict[int, float] = {}

@app.get("/live", response_class=HTMLResponse)
async def live_camera(request: Request):
    # Pasamos root_path por si en tus templates quieres usarlo
    return templates.TemplateResponse("camera.html", {"request": request})

@app.websocket("/ws/{camera_id}")
async def websocket_endpoint(websocket: WebSocket, camera_id: int = 0):
    await websocket.accept()

    # URL de cámara: 0 = webcam local, >0 cámaras RTSP (ajusta a tu topología)
    camera_url = camera_id if camera_id == 0 else f"rtsp://admin:password@192.168.1.{100 + camera_id}/live.sdp"

    with camera_lock:
        cap = active_cameras.get(camera_id)
        if cap is None:
            cap = cv2.VideoCapture(camera_url)
            if not cap.isOpened():
                await websocket.close(code=1001, reason=f"No se pudo abrir la cámara {camera_id}")
                return
            active_cameras[camera_id] = cap

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                # Frame de “offline” si falla la captura
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, f"CAM {camera_id} OFFLINE", (50, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                danger_detected = False
            else:
                # Procesar detección
                frame, danger_detected, _ = detect_dangers(frame)

            # Redimensionamos para rendimiento y ancho estable
            frame = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_AREA)

            # Si hay alerta y cooldown cumplido → enviar mensaje de texto (para UI)
            if danger_detected:
                now = time.time()
                last = _last_alert_sent.get(camera_id, 0)
                if now - last >= ALERT_COOLDOWN_SEC:
                    _last_alert_sent[camera_id] = now
                    # Enviamos JSON corto; el front puede mirar "type":"alert"
                    await websocket.send_text(json.dumps({
                        "type": "alert",
                        "camera_id": camera_id,
                        "ts": int(now)
                    }))

            # Enviar frame como JPEG binario
            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                # Si por algún motivo no codifica, enviamos un frame “negro”
                fallback = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(fallback, "CODIFICACION FALLIDA", (60, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                _, buffer = cv2.imencode(".jpg", fallback)

            await websocket.send_bytes(buffer.tobytes())
            await asyncio.sleep(0.05)  # ~20 FPS
    except Exception as e:
        # Log básico a stdout (revisable en logs de prod)
        print(f"[WS] Error en cámara {camera_id}: {e}")
    finally:
        with camera_lock:
            cap = active_cameras.pop(camera_id, None)
            try:
                if cap is not None:
                    cap.release()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass

# ───────────────────────── Página de resultados (si la usas) ─────────────────────────
@app.get("/results/{image_id}", response_class=HTMLResponse)
async def analysis_results(request: Request, image_id: str):
    return templates.TemplateResponse("analysis.html", {"request": request, "image_id": image_id})

# ───────────────────────── Entrypoint ─────────────────────────
if __name__ == "__main__":
    import uvicorn
    # En prod normalmente usarás un servidor ASGI (gunicorn/uvicorn workers). Este es para local.
    uvicorn.run(app, host="0.0.0.0", port=8000)
