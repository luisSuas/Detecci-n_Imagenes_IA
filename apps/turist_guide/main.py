# apps/turist_guide/main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
from openai import OpenAI
import requests
import os
import re
import json
from datetime import datetime

# ========= Config básica =========
BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"

app = FastAPI(
    title="TurisBot GT",
    description="API para el sistema de chatbots turísticos",
    version="1.0.0"
)

# CORS amplio (ajusta si necesitas restringir)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sirve /static relativo al montaje de esta app (p.ej. /turist-guide/static)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ========= ENV / APIs externas =========
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
MAPBOX_ACCESS_TOKEN = os.getenv("MAPBOX_ACCESS_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")  # default moderno

# Cliente OpenAI (tolerante a ausencia de API key)
client: Optional[OpenAI] = None
if OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        print(f"✅ OpenAI listo (modelo chat: {OPENAI_CHAT_MODEL})")
    except Exception as e:
        print(f"⚠️ No se pudo iniciar OpenAI: {e}")
        client = None
else:
    print("ℹ️ OPENAI_API_KEY no configurada; usaré respuestas de respaldo.")

# ========= Modelos de datos =========
class ChatbotCreate(BaseModel):
    name: str
    country: str

class Message(BaseModel):
    message: str
    chatbot_id: str
    language: str = "es"

class WeatherRequest(BaseModel):
    lat: float
    lon: float

# ========= Memoria simple (demo) =========
chatbots = {
    "1": {
        "id": "1",
        "name": "Machu Picchu",
        "country": "Perú",
        "category": "historical",
        "description": "Antigua ciudad inca en las montañas de los Andes",
        "coordinates": {"lat": -13.163, "lng": -72.545},
        "itinerary": [
            {"time": "09:00 AM", "activity": "Llegada a la entrada principal de Machu Picchu"},
            {"time": "09:30 AM", "activity": "Visita a la Casa del Guardián para vistas panorámicas"},
            {"time": "10:30 AM", "activity": "Recorrido por la Plaza Principal"},
            {"time": "11:30 AM", "activity": "Exploración del Templo del Sol"},
            {"time": "12:30 PM", "activity": "Almuerzo en zona designada"},
            {"time": "02:00 PM", "activity": "Visita al Templo de las Tres Ventanas"},
            {"time": "03:00 PM", "activity": "Recorrido por el Intihuatana (Reloj Solar)"},
            {"time": "04:00 PM", "activity": "Exploración del Templo del Cóndor"},
            {"time": "05:00 PM", "activity": "Tiempo libre para fotos y contemplación"},
            {"time": "05:45 PM", "activity": "Preparación para salida"}
        ]
    }
}
messages = {
    "1": [
        {"role": "assistant", "content": "¡Hola! Soy tu guía virtual para Machu Picchu. ¿En qué puedo ayudarte hoy? Puedo contarte sobre la historia, darte información sobre el clima o ayudarte a planificar tu itinerario.", "timestamp": "10:00 AM"}
    ]
}

# ========= Utilidades =========
def _inject_base_href(html: str, base_href: str) -> str:
    """
    Inserta <base href="..."> en <head> si falta, y reescribe href/src que empiecen con '/static'
    para que respeten el subpath de montaje (p.ej. /turist-guide).
    """
    if not html:
        return html
    # Inserta <base ...> si no existe
    if "<base " not in html.lower():
        html = re.sub(
            r"(<head[^>]*>)",
            r'\1\n  <base href="%s">' % base_href.rstrip("/") + "/",
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    # Reescribe /static → {base}/static (solo cuando está como ruta absoluta)
    html = re.sub(r'((href|src)=["\'])/static/', r'\1' + base_href.rstrip("/") + '/static/', html, flags=re.IGNORECASE)
    return html

def _root_path(request: Request) -> str:
    # Cuando se monta con .mount("/turist-guide", app) Starlette fija root_path
    rp = request.scope.get("root_path") or "/"
    return rp if rp.endswith("/") else rp + "/"

def get_weather(lat: float, lon: float):
    try:
        if not OPENWEATHER_API_KEY:
            raise RuntimeError("No OPENWEATHER_API_KEY")
        url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang=es"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                "temperature": data["main"]["temp"],
                "description": data["weather"][0]["description"],
                "icon": data["weather"][0]["icon"]
            }
    except Exception as e:
        print(f"Weather fallback: {e}")

    # Respaldo
    return {"temperature": 22, "description": "Soleado", "icon": "01d"}

def _chat_completion(messages, max_tokens=500, temperature=0.7) -> str:
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"OpenAI error: {e}")
        return None

def generate_ai_response(prompt: str, context: str, language: str = "es") -> str:
    system_message = f"Eres un guía turístico experto. Contexto: {context}. Responde en {language}."
    out = _chat_completion(
        [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ],
        max_tokens=500,
        temperature=0.7
    )
    if out:
        return out
    # Respaldo si no hay OpenAI
    return "Puedo ayudarte con historia, clima e itinerarios del destino. (modo sin IA)"

def get_place_info(place_name: str, country: str):
    """Obtiene info del lugar vía IA; respalda con valores por defecto si no hay IA."""
    prompt = (
        f"Proporciona información detallada sobre {place_name} en {country}.\n"
        "Incluye:\n"
        "1. Coordenadas GPS en JSON: {\"lat\": valor, \"lng\": valor}\n"
        "2. Una descripción breve (<=150 caracteres)\n"
        "3. Categoría: historical | beach | mountain | city | park\n"
        "Responde SOLO en JSON con: coordinates, description, category."
    )
    out = _chat_completion(
        [
            {"role": "system", "content": "Eres un asistente turístico que proporciona información precisa sobre lugares."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=400,
        temperature=0.3
    )
    if out:
        try:
            m = re.search(r'\{.*\}', out, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            print(f"Parse place_info error: {e}")

    # Respaldo
    return {
        "coordinates": {"lat": 0, "lng": 0},
        "description": f"Lugar turístico {place_name} en {country}",
        "category": "historical"
    }

def generate_itinerary(place_name: str, place_description: str, language: str = "es"):
    prompt = (
        f"Crea un itinerario de un día para visitar {place_name} ({place_description}). "
        "Debe tener entre 9 y 11 actividades entre 9:00 AM y 6:00 PM. "
        "Formato: líneas 'HH:MM AM/PM - Descripción'. Responde en " + language + "."
    )
    it_text = _chat_completion(
        [
            {"role": "system", "content": "Eres un planificador de itinerarios turísticos experto."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=600,
        temperature=0.8
    )
    if not it_text:
        return generate_default_itinerary(place_name)

    items = []
    for raw in it_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(ch.isdigit() for ch in line) and ("AM" in line or "PM" in line):
            # separador tras la hora
            m = re.match(r'^([0-9]{1,2}:[0-9]{2}\s*[AP]M)\s*[-–]\s*(.+)$', line, flags=re.IGNORECASE)
            if m:
                items.append({"time": m.group(1).upper().replace("AM", "AM").replace("PM", "PM"),
                              "activity": m.group(2).strip()})
    return items[:11] if items else generate_default_itinerary(place_name)

def generate_default_itinerary(place_name: str):
    base_times = [
        "09:00 AM","10:00 AM","11:00 AM","12:00 PM",
        "01:00 PM","02:00 PM","03:00 PM","04:00 PM",
        "05:00 PM","06:00 PM"
    ]
    base_activities = [
        "Llegada al destino","Recorrido por la zona principal","Visita a puntos de interés",
        "Almuerzo en lugar recomendado","Tour guiado por áreas históricas","Tiempo libre para exploración",
        "Visita a miradores panorámicos","Recorrido por tiendas de artesanías","Descanso y refrigerio",
        "Preparación para la salida"
    ]
    return [{"time": t, "activity": f"{base_activities[i]} en {place_name}"} for i, t in enumerate(base_times)]

def get_recommendations(chatbot_id: str):
    cb = chatbots.get(chatbot_id)
    if not cb:
        return []
    cat = cb.get("category")
    mapping = {
        "historical": [
            {"type": "restaurant", "name": "Restaurante Local", "icon": "utensils"},
            {"type": "hotel", "name": "Hotel Cercano", "icon": "hotel"},
            {"type": "guide", "name": "Guía Local", "icon": "user"},
            {"type": "shop", "name": "Tienda de Artesanías", "icon": "store"}
        ],
        "beach": [
            {"type": "restaurant", "name": "Restaurante Playero", "icon": "utensils"},
            {"type": "hotel", "name": "Resort en la Playa", "icon": "hotel"},
            {"type": "activity", "name": "Tours Acuáticos", "icon": "ship"},
            {"type": "shop", "name": "Tienda de Surf", "icon": "store"}
        ],
        "mountain": [
            {"type": "restaurant", "name": "Refugio de Montaña", "icon": "utensils"},
            {"type": "hotel", "name": "Albergue", "icon": "hotel"},
            {"type": "guide", "name": "Guía de Montaña", "icon": "user"},
            {"type": "activity", "name": "Equipamiento de Senderismo", "icon": "hiking"}
        ],
        "city": [
            {"type": "restaurant", "name": "Restaurante Urbano", "icon": "utensils"},
            {"type": "hotel", "name": "Hotel Céntrico", "icon": "hotel"},
            {"type": "transport", "name": "Transporte Turístico", "icon": "bus"},
            {"type": "shop", "name": "Centro Comercial", "icon": "store"}
        ],
        "park": [
            {"type": "restaurant", "name": "Cafetería del Parque", "icon": "utensils"},
            {"type": "hotel", "name": "Eco-Lodge", "icon": "hotel"},
            {"type": "guide", "name": "Guía Naturalista", "icon": "user"},
            {"type": "activity", "name": "Tour de Observación", "icon": "binoculars"}
        ]
    }
    return mapping.get(cat, [])

# ========= Rutas UI =========
@app.get("/", response_class=HTMLResponse)
async def ui_root(request: Request):
    """
    Sirve index.html e inyecta <base href="{root_path}"> para que los assets funcionen
    cuando se monta bajo /turist-guide (o cualquier subruta).
    """
    if INDEX_FILE.exists():
        html = INDEX_FILE.read_text(encoding="utf-8")
        base = _root_path(request)
        html = _inject_base_href(html, base)
        return HTMLResponse(content=html, status_code=200)
    # fallback si no hay index.html
    return HTMLResponse("<h2>Turist-Guide</h2><p>UI no encontrada.</p>", status_code=200)

@app.get("/index.html", response_class=HTMLResponse)
async def ui_index_alias(request: Request):
    return await ui_root(request)

@app.get("/healthz")
async def healthz():
    return {"ok": True}

# ========= Endpoints API =========
@app.get("/chatbots")
async def get_chatbots():
    return list(chatbots.values())

@app.post("/chatbots")
async def create_chatbot(chatbot: ChatbotCreate):
    chatbot_id = str(len(chatbots) + 1)
    place_info = get_place_info(chatbot.name, chatbot.country)
    itinerary = generate_itinerary(chatbot.name, place_info["description"], "es")
    chatbots[chatbot_id] = {
        "id": chatbot_id,
        "name": chatbot.name,
        "country": chatbot.country,
        "category": place_info["category"],
        "description": place_info["description"],
        "coordinates": place_info["coordinates"],
        "itinerary": itinerary
    }
    messages[chatbot_id] = []
    return chatbots[chatbot_id]

@app.get("/chatbots/{chatbot_id}")
async def get_chatbot(chatbot_id: str):
    if chatbot_id not in chatbots:
        raise HTTPException(status_code=404, detail="Chatbot no encontrado")
    return chatbots[chatbot_id]

@app.get("/chatbots/{chatbot_id}/messages")
async def get_messages(chatbot_id: str):
    if chatbot_id not in messages:
        raise HTTPException(status_code=404, detail="Chatbot no encontrado")
    return messages[chatbot_id]

@app.post("/chatbots/{chatbot_id}/messages")
async def create_message(chatbot_id: str, message: Message):
    if chatbot_id not in chatbots:
        raise HTTPException(status_code=404, detail="Chatbot no encontrado")

    user_message = {
        "role": "user",
        "content": message.message,
        "timestamp": datetime.now().strftime("%H:%M")
    }
    messages.setdefault(chatbot_id, []).append(user_message)

    cb = chatbots[chatbot_id]
    context = f"Lugar: {cb['name']} en {cb['country']}. Categoría: {cb['category']}. Descripción: {cb['description']}"

    ai_response = generate_ai_response(message.message, context, message.language)

    assistant_message = {
        "role": "assistant",
        "content": ai_response,
        "timestamp": datetime.now().strftime("%H:%M")
    }
    messages[chatbot_id].append(assistant_message)
    return assistant_message

@app.post("/weather")
async def get_weather_data(request: WeatherRequest):
    return get_weather(request.lat, request.lon)

@app.get("/chatbots/{chatbot_id}/recommendations")
async def get_recommendations_endpoint(chatbot_id: str):
    if chatbot_id not in chatbots:
        raise HTTPException(status_code=404, detail="Chatbot no encontrado")
    return get_recommendations(chatbot_id)

@app.get("/mapbox-token")
async def get_mapbox_token():
    return {"token": MAPBOX_ACCESS_TOKEN or ""}

@app.get("/chatbots/{chatbot_id}/itinerary")
async def get_itinerary(chatbot_id: str):
    if chatbot_id not in chatbots:
        raise HTTPException(status_code=404, detail="Chatbot no encontrado")
    return chatbots[chatbot_id].get("itinerary", [])

# Nota: no arrancamos uvicorn aquí; el HUB montará esta app.
# Si quieres ejecutarla sola localmente:
#   uvicorn apps.turist_guide.main:app --reload --port 8010
