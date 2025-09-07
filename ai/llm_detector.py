import os
import json
import base64
import mimetypes
from typing import Dict, Any, List

import cv2


CLRS = {
    'fuga_techo': (255, 0, 0),          # rojo
    'filtracion_pared': (0, 255, 255),  # amarillo
    'equipo_oxidado': (0, 165, 255),    # naranja
    'tuberia_rota': (255, 0, 0),        # rojo
    'cable_expuesto': (255, 0, 255),    # magenta
    'enchufe_danado': (0, 200, 255),    # cian
    'pared_rajada': (160, 82, 45),      # café
}

# Extiende colores para nuevas clases del modo LLM
CLRS.update({
    'llave_goteando': (0, 128, 255),      # naranja-azul
    'trampa_fuga': (0, 128, 128),         # teal
    'interruptor_danado': (153, 50, 204), # morado
    'tablero_abierto': (139, 0, 0),       # rojo oscuro
    'luminaria_falla': (184, 134, 11),    # dorado
    'loseta_suelta': (205, 133, 63),      # peru
    'piso_desgastado': (112, 128, 144),   # slate gray
    'ventana_rota': (70, 130, 180),       # steel blue
    'puerta_danada': (160, 82, 45),       # cafe
    'fuga_gas': (46, 139, 87),            # sea green
    'filtro_hvac_sucio': (105, 105, 105), # dim gray
    'unidad_ac_congelada': (135, 206, 250), # light sky blue
    'moho_techo': (85, 107, 47),          # olive drab
    'humedad_sotano': (0, 191, 255),      # deep sky blue
})


def _data_url_for_image(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        ext = os.path.splitext(path)[1].lower()
        mime = 'image/png' if ext == '.png' else 'image/jpeg'
    with open(path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')
    return f"data:{mime};base64,{b64}"


def _safe_json(text: str) -> Dict[str, Any]:
    # Intenta recortar antes/después si el modelo envolvió el JSON con texto
    text = text.strip()
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        text = text[start:end+1]
    return json.loads(text)


def _draw_boxes(orig_path: str, save_path: str, items: List[Dict[str, Any]]):
    img = cv2.imread(orig_path)
    if img is None:
        return False
    H, W = img.shape[:2]
    drew = False
    for it in items or []:
        bbox = it.get('bbox_norm') or it.get('bbox')
        if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            x1n, y1n, x2n, y2n = [max(0.0, min(1.0, float(v))) for v in bbox]
            x1, y1 = int(x1n * W), int(y1n * H)
            x2, y2 = int(x2n * W), int(y2n * H)
        except Exception:
            continue
        label = it.get('problema') or 'incidencia'
        conf = it.get('confianza')
        try:
            conf_txt = f" {float(conf):.1f}%" if conf is not None else ''
        except Exception:
            conf_txt = ''
        color = CLRS.get(label, (0, 255, 0))
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, f"{label}{conf_txt}", (x1, max(12, y1-6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        drew = True
    # Si no dibujamos nada, igual guardamos una copia
    cv2.imwrite(save_path, img)
    return True


def analyze_image_to_structured(client, model: str, image_path: str, zona: str = "", results_dir: str = "static/results") -> Dict[str, Any]:
    if not os.path.exists(image_path):
        return {'error': 'La imagen no existe'}

    # Prepara salida de imagen procesada
    os.makedirs(results_dir, exist_ok=True)
    filename = os.path.basename(image_path)
    processed_path = os.path.join(results_dir, filename)

    # Construye prompt
    classes = ["fuga_techo", "filtracion_pared", "equipo_oxidado", "tuberia_rota"]
    zone_hint = f"Zona sugerida por el usuario: {zona}." if zona else ""
    sys_prompt = (
        "Eres un analista experto en mantenimiento e infraestructura. "
        "Analiza la imagen y devuelve SOLO un JSON válido con el siguiente esquema. "
        "Usa clases del conjunto: fuga_techo, filtracion_pared, equipo_oxidado, tuberia_rota. "
        "Restringe 'prioridad' a Alta|Media|Baja y 'urgencia_global' a inmediata|programada. "
        "Si puedes, incluye 'bbox_norm' en cada incidencia con [x1,y1,x2,y2] normalizados 0..1. "
        "Sé conservador con la confianza; si dudas, usa Media o Baja."
    )
    user_instructions = f"{zone_hint}\nDevuelve como máximo 4 incidencias."

    schema_hint = {
        "resumen_inspeccion": {
            "prioridad_global": "Alta|Media|Baja",
            "urgencia_global": "inmediata|programada",
            "zona": "Texto breve (si puedes inferir)",
            "detecciones": "entero",
            "acciones_recomendadas_globales": ["3 a 5 acciones concretas"]
        },
        "reporte_incidencia": [
            {
                "problema": "una de: " + ", ".join(classes),
                "prioridad": "Alta|Media|Baja",
                "confianza": 0.0,
                "descripcion": "1-2 frases",
                "bbox_norm": [0.0, 0.0, 1.0, 1.0]
            }
        ],
        "solucion": [
            {
                "problema": "coincidente con reporte_incidencia[i].problema",
                "pasos": ["3-6 pasos operativos y seguros"],
                "workers_detalle": {"profesional": "rol recomendado", "SLA": "tiempo objetivo"}
            }
        ]
    }

    data_url = _data_url_for_image(image_path)

    # ---- Ampliacion del catalogo (modo LLM) ----
    classes = [
        # Plomeria / agua
        "tuberia_rota", "fuga_techo", "filtracion_pared", "llave_goteando", "trampa_fuga",
        # Electricidad
        "cable_expuesto", "enchufe_danado", "interruptor_danado", "tablero_abierto", "luminaria_falla",
        # Estructura / civil
        "pared_rajada", "loseta_suelta", "piso_desgastado", "ventana_rota", "puerta_danada",
        # Gas / HVAC
        "fuga_gas", "filtro_hvac_sucio", "unidad_ac_congelada",
        # Otros
        "equipo_oxidado", "moho_techo", "humedad_sotano"
    ]

    # Reforzamos el prompt con definiciones (sin acentos para robustez)
    sys_prompt = (
        "Eres un analista experto en mantenimiento de hogares y edificios. "
        "Analiza la imagen y devuelve SOLO un JSON valido con el esquema indicado. "
        "Usa exclusivamente estas clases: " + ", ".join(classes) + ". "
        "'enchufe_danado' = placa/tomacorriente flojo/roto/salido; 'cable_expuesto' = conductores sin aislamiento visible; "
        "'pared_rajada' = grietas visibles; 'filtracion_pared' = manchas de humedad/moho por agua. "
        "Restringe 'prioridad' a Alta|Media|Baja y 'urgencia_global' a inmediata|programada. "
        "Incluye 'bbox_norm' con [x1,y1,x2,y2] normalizados 0..1 cuando sea viable. "
        "Se conservador con la confianza; si dudas, usa Media o Baja."
    )

    # Actualiza el esquema de ejemplo con el catalogo ampliado
    schema_hint = {
        "resumen_inspeccion": {
            "prioridad_global": "Alta|Media|Baja",
            "urgencia_global": "inmediata|programada",
            "zona": "Texto breve (si puedes inferir)",
            "detecciones": "entero",
            "acciones_recomendadas_globales": ["3 a 5 acciones concretas"]
        },
        "reporte_incidencia": [
            {
                "problema": "una de: " + ", ".join(classes),
                "prioridad": "Alta|Media|Baja",
                "confianza": 0.0,
                "descripcion": "1-2 frases",
                "bbox_norm": [0.0, 0.0, 1.0, 1.0]
            }
        ],
        "solucion": [
            {
                "problema": "coincidente con reporte_incidencia[i].problema",
                "pasos": ["3-6 pasos operativos y seguros"],
                "workers_detalle": {"profesional": "rol recomendado", "SLA": "tiempo objetivo"}
            }
        ]
    }

    # Llamada a GPT (visión)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_instructions + "\nEsquema esperado (ejemplo):\n" + json.dumps(schema_hint, ensure_ascii=False)},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ],
        temperature=0.2,
        max_tokens=800
    )

    text = (resp.choices[0].message.content or "").strip() if resp and resp.choices else ""
    if not text:
        return {'error': 'Respuesta vacía del modelo'}

    try:
        obj = _safe_json(text)
    except Exception as e:
        return {'error': f'No se pudo parsear JSON: {str(e)}'}

    # Normaliza campos mínimos
    res_ins = obj.get('resumen_inspeccion') or {}
    rep = obj.get('reporte_incidencia') or []
    sol = obj.get('solucion') or []

    # Dibuja cajas si están
    drew = False
    if isinstance(rep, list) and rep:
        try:
            drew = _draw_boxes(image_path, processed_path, rep)
        except Exception:
            drew = False

    if not drew:
        # Copia simple si no hay cajas o falló dibujo
        try:
            img = cv2.imread(image_path)
            if img is not None:
                cv2.imwrite(processed_path, img)
        except Exception:
            pass

    # Construir 'analysis' básico para compatibilidad
    def _build_analysis(items: List[Dict[str, Any]]):
        total = len(items or [])
        avg = 0.0
        if total:
            vals = []
            for it in items:
                c = it.get('confianza')
                try:
                    c = float(c)
                except Exception:
                    c = 0.0
                if c > 1.0:  # si vino en porcentaje
                    c = c / 100.0
                vals.append(max(0.0, min(1.0, c)))
            avg = sum(vals)/len(vals) if vals else 0.0
        class_dist = {}
        severity_dist = {}
        for it in items or []:
            cls = (it.get('problema') or '').lower()
            pr  = (it.get('prioridad') or '').lower()
            if cls:
                class_dist[cls] = class_dist.get(cls, 0) + 1
            if pr:
                severity_dist[pr] = severity_dist.get(pr, 0) + 1
        return {
            'total_problems': total,
            'severity_distribution': severity_dist,
            'class_distribution': class_dist,
            'average_confidence': avg
        }

    analysis = _build_analysis(rep if isinstance(rep, list) else [])

    # Respuesta compatible con el frontend
    return {
        'original_image': image_path.replace('\\', '/'),
        'processed_image': processed_path.replace('\\', '/'),
        'resumen_inspeccion': {
            'prioridad_global': res_ins.get('prioridad_global') or 'Baja',
            'urgencia_global': res_ins.get('urgencia_global') or 'programada',
            'zona': res_ins.get('zona') or zona or 'N/D',
            'detecciones': res_ins.get('detecciones') or (len(rep) if isinstance(rep, list) else 0),
            'acciones_recomendadas_globales': res_ins.get('acciones_recomendadas_globales') or []
        },
        'analysis': analysis,
        'reporte_incidencia': rep,
        'solucion': sol
    }
