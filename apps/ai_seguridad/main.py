import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Request, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse, HTMLResponse
from ultralytics import YOLO
import asyncio
import uuid
import os
import base64
from pathlib import Path
import json
from typing import Dict
import threading

app = FastAPI(title="Sistema de Seguridad", description="Detección de objetos peligrosos en tiempo real")

# ───────────────────────── Configuración de directorios (robusto para sub-app) ─────────────────────────
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Crear directorios si no existen
os.makedirs(STATIC_DIR / "css", exist_ok=True)
os.makedirs(STATIC_DIR / "js", exist_ok=True)
os.makedirs(STATIC_DIR / "uploads", exist_ok=True)

# ───────────────────────── Carga perezosa del modelo (ahorra RAM en 1 instancia) ───────────────────────
MODEL_PATH = BASE_DIR / "yolov8n.pt"
_model = None
_model_lock = threading.Lock()

def get_model() -> YOLO:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = YOLO(str(MODEL_PATH))  # CPU por defecto si no hay GPU
    return _model

# Clases consideradas peligrosas (personalizable)
DANGER_CLASSES = ['knife', 'gun', 'pistol', 'weapon', 'firearm', 'rifle']
SAFETY_CLASSES = ['person', 'backpack', 'handbag', 'suitcase', 'cell phone']

# Función para detección y alertas
def detect_dangers(frame):
    model = get_model()
    results = model(frame, verbose=False)
    danger_detected = False
    detected_objects = []
    
    for result in results:
        for box in result.boxes:
            class_id = int(box.cls)
            class_name = model.names[class_id]
            confidence = float(box.conf)
            
            if class_name in DANGER_CLASSES and confidence > 0.5:
                danger_detected = True
                # Dibujar cuadro de alerta
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                
                # Etiqueta de alerta
                label = f"ALERTA! {class_name.upper()} {confidence:.2f}"
                cv2.putText(frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                
                # Guardar detección
                detected_objects.append({
                    "class": class_name,
                    "confidence": confidence,
                    "position": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                })
            elif class_name in SAFETY_CLASSES and confidence > 0.5:
                # Dibujar cuadro de seguridad
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Etiqueta de seguridad
                label = f"{class_name.upper()} {confidence:.2f}"
                cv2.putText(frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    # Banner de alerta general
    if danger_detected:
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 50), (0, 0, 255), -1)
        cv2.putText(frame, "ZONA PELIGROSA DETECTADA!", (100, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    return frame, danger_detected, detected_objects

# Página principal
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Procesamiento de imágenes (URL estática consciente del prefijo de montaje)
@app.post("/upload/image")
async def upload_image(request: Request, file: UploadFile = File(...)):
    image_data = await file.read()
    nparr = np.frombuffer(image_data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Detectar peligros
    processed_frame, danger_detected, detected_objects = detect_dangers(frame)
    
    # Guardar imagen procesada
    rel_filename = f"static/uploads/processed_{uuid.uuid4()}.jpg"
    abs_path = STATIC_DIR / "uploads" / Path(rel_filename).name
    cv2.imwrite(str(abs_path), processed_frame)
    
    # Convertir a base64 para mostrar en la interfaz
    _, img_encoded = cv2.imencode('.jpg', processed_frame)
    img_base64 = base64.b64encode(img_encoded).decode('utf-8')
    
    # Construir URL que respete el root_path (p. ej., /ai-seguridad)
    root = request.scope.get("root_path", "")
    image_url = f"{root}/static/uploads/{abs_path.name}"
    
    return {
        "danger_detected": danger_detected,
        "detected_objects": detected_objects,
        "image_base64": img_base64,
        "image_url": image_url
    }

# Procesamiento de videos (URL estática consciente del prefijo de montaje)
@app.post("/upload/video")
async def upload_video(request: Request, file: UploadFile = File(...)):
    # Guardar video temporal
    temp_name = f"temp_{uuid.uuid4()}.mp4"
    temp_file = STATIC_DIR / "uploads" / temp_name
    with open(temp_file, "wb") as buffer:
        buffer.write(await file.read())
    
    # Procesar video
    cap = cv2.VideoCapture(str(temp_file))
    if not cap.isOpened():
        return {"error": "No se pudo abrir el video"}
    
    # Configurar video de salida
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    out_name = f"output_{uuid.uuid4()}.mp4"
    out_file = STATIC_DIR / "uploads" / out_name
    out = cv2.VideoWriter(
        str(out_file),
        fourcc,
        fps,
        (width, height)
    )
    
    alert_in_video = False
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        processed_frame, danger_detected, _ = detect_dangers(frame)
        if danger_detected:
            alert_in_video = True
        out.write(processed_frame)
    
    cap.release()
    out.release()
    try:
        os.remove(temp_file)  # Eliminar archivo temporal
    except Exception:
        pass
    
    root = request.scope.get("root_path", "")
    return {
        "alert": alert_in_video,
        "processed_video": f"{root}/static/uploads/{out_name}"
    }

# Vista de cámara en tiempo real
# Variables globales para manejar múltiples cámaras
active_cameras: Dict[int, cv2.VideoCapture] = {}
camera_lock = threading.Lock()

@app.get("/live", response_class=HTMLResponse)
async def live_camera(request: Request):
    return templates.TemplateResponse("camera.html", {"request": request})

@app.websocket("/ws/{camera_id}")
async def websocket_endpoint(websocket: WebSocket, camera_id: int = 0):
    await websocket.accept()
    
    # Configurar la cámara (0 para webcam local, otros para cámaras IP)
    camera_url = camera_id if camera_id == 0 else f"rtsp://admin:password@192.168.1.{100 + camera_id}/live.sdp"
    
    with camera_lock:
        if camera_id not in active_cameras:
            cap = cv2.VideoCapture(camera_url)
            if not cap.isOpened():
                await websocket.close(code=1001, reason=f"No se pudo abrir la cámara {camera_id}")
                return
            active_cameras[camera_id] = cap
    
    try:
        while True:
            ret, frame = active_cameras[camera_id].read()
            if not ret:
                # Crear frame de error si falla la captura
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, f"CAM {camera_id} OFFLINE", (50, 240), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            else:
                # Procesar detección de objetos
                frame, danger_detected, _ = detect_dangers(frame)
            
            # Reducir tamaño para mejor rendimiento
            frame = cv2.resize(frame, (640, 480))
            
            # Codificar y enviar
            _, buffer = cv2.imencode('.jpg', frame)
            await websocket.send_bytes(buffer.tobytes())
            await asyncio.sleep(0.05)  # ~20 FPS
            
    except Exception as e:
        print(f"Error en cámara {camera_id}: {e}")
    finally:
        with camera_lock:
            if camera_id in active_cameras:
                active_cameras[camera_id].release()
                del active_cameras[camera_id]
        await websocket.close()

# Página de análisis de resultados
@app.get("/results/{image_id}", response_class=HTMLResponse)
async def analysis_results(request: Request, image_id: str):
    return templates.TemplateResponse("analysis.html", {"request": request, "image_id": image_id})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
