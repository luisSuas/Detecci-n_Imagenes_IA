import cv2
import numpy as np
from ultralytics import YOLO
import os
import logging
from datetime import datetime
from pathlib import Path  # ⟵ NUEVO

# ==== Mapas y reglas para “sentido común” ====
ALIASES = {
    "FUGA TECHO": "fuga_techo",
    "FILTRACION PARED": "filtracion_pared",
    "EQUIPO OXIDADO": "equipo_oxidado",
    "TUBERIA ROTA": "tuberia_rota",
}

CRITICAS = {"tuberia_rota", "fuga_techo"}  # puedes ajustar
PRIO_RANK = {"Alta": 3, "Media": 2, "Baja": 1}

CONCEPTOS = {
    "fuga_techo": "Entrada de agua por cubierta/techo; riesgo para plafones y equipos.",
    "filtracion_pared": "Humedad/moho en muros por ingreso de agua.",
    "equipo_oxidado": "Corrosión que compromete integridad y funcionamiento.",
    "tuberia_rota": "Fuga continua por rotura de tubería; posible daño eléctrico/estructural."
}

CATEGORIAS = {
    "fuga_techo": ["Impermeabilización", "Mantenimiento"],
    "filtracion_pared": ["Mantenimiento", "Impermeabilización"],
    "equipo_oxidado": ["Mecánica/Mantenimiento", "Seguridad"],
    "tuberia_rota": ["Plomería", "Mantenimiento"]
}

ACCIONES_BASE = {
    "fuga_techo": [
        "Inspeccionar cubierta y sellar puntos de ingreso",
        "Aplicar sistema de impermeabilización",
        "Revisar desagües pluviales y despejar obstrucciones"
    ],
    "filtracion_pared": [
        "Detectar y corregir la fuente de humedad",
        "Aplicar selladores o pintura impermeabilizante",
        "Mejorar ventilación del área afectada"
    ],
    "equipo_oxidado": [
        "Desenergizar y asegurar el equipo (si aplica)",
        "Remover óxido y aplicar anticorrosivo",
        "Evaluar sustitución de partes comprometidas"
    ],
    "tuberia_rota": [
        "Cerrar válvulas de paso cercanas",
        "Aislar y señalizar el área",
        "Sustituir el tramo afectado y verificar presión"
    ]
}

# === Palabras clave para inferir zona desde el nombre del archivo ===
ZONA_KEYWORDS = {
    "electrico": "Cuarto eléctrico",
    "eléctrico": "Cuarto eléctrico",
    "tablero": "Tablero eléctrico",
    "ups": "Sala UPS",
    "rack": "Sala de racks",
    "servidor": "Centro de datos",
    "server": "Centro de datos",
    "sotano": "Sótano",
    "sótano": "Sótano",
    "bodega": "Bodega",
    "pasillo": "Pasillo",
    "banio": "Baño",
    "baño": "Baño",
    "baño": "Baño",
    "techo": "Techo / Cubierta",
    "azotea": "Azotea",
    "estacionamiento": "Estacionamiento",
    "oficina": "Oficina",
    "exterior": "Exterior",
    "maquinas": "Cuarto de máquinas",
    "máquinas": "Cuarto de máquinas",
    "caldera": "Sala de calderas",
    "planta": "Sala de planta"
}


class ProblemDetector:
    def __init__(self, model_path=None):
        """Inicializador robusto con múltiples fallbacks"""
        self.model = None
        self.class_names = {}
        self.problem_descriptions = {}

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        try:
            self._setup_problem_descriptions()
            self._load_model(model_path)
            self.logger.info("Detector inicializado correctamente")
        except Exception as e:
            self.logger.error(f"Error crítico al inicializar el detector: {str(e)}")
            raise

    # ----------------- Carga del modelo -----------------
    def _load_model(self, model_path=None):
        """
        Carga el modelo con alternativas y verificación.
        Ahora usa rutas ABSOLUTAS basadas en este archivo (apps/ai_detect/...).
        """
        base_dir = Path(__file__).resolve().parent  # apps/ai_detect
        # Permite override por variable de entorno
        env_path = os.getenv("AI_DETECT_MODEL") or os.getenv("MODEL_PATH")

        # Normaliza a Path si viene str; ignora None.
        def _p(x):
            if not x:
                return None
            x = Path(x)
            # Si es relativo, inténtalo relativo a este archivo y al cwd
            return x if x.is_absolute() else (base_dir / x)

        candidates = [
            _p(model_path),
            _p(env_path),
            base_dir / "modelos" / "problemas_infraestructura.pt",     # ⟵ tu modelo real
            base_dir / "yolov8n.pt",
            base_dir / "yolov8s.pt",
            # Por si el cwd es el repo raíz
            Path("apps/ai_detect/modelos/problemas_infraestructura.pt"),
            Path("modelos/problemas_infraestructura.pt"),
        ]

        tried = []
        for cand in candidates:
            if not cand:
                continue
            cand = cand.resolve()
            tried.append(str(cand))
            try:
                if not cand.exists():
                    self.logger.warning(f"Modelo no encontrado: {cand}")
                    continue
                if cand.stat().st_size < 1024 * 1024:  # <1MB probablemente no es un .pt válido
                    self.logger.warning(f"Modelo demasiado pequeño: {cand}")
                    continue

                self.model = YOLO(str(cand))
                self.class_names = self.model.names
                self.logger.info(f"Modelo cargado exitosamente: {cand}")
                self.logger.info(f"📦 Clases del modelo: {self.class_names}")
                return
            except Exception as e:
                self.logger.error(f"Error al cargar {cand}: {e}")
                continue

        # Si llegó aquí, no se cargó
        msg = (
            "No se pudo cargar ningún modelo YOLO válido.\n"
            "Rutas intentadas:\n- " + "\n- ".join(tried)
        )
        raise RuntimeError(msg)

    # ----------------- Catálogo base (sin duplicados) -----------------
    def _setup_problem_descriptions(self):
        """Configuración completa de problemas y soluciones"""
        self.problem_descriptions = {
            'cable_expuesto': {
                'description': 'Cable eléctrico expuesto que representa riesgo de electrocución',
                'severity': 'critica',
                'solutions': [
                    'Cortar energía en el área inmediatamente',
                    'Reparar con materiales aislantes adecuados',
                    'Reemplazar cable si el daño es extenso'
                ],
                'color': (255, 0, 0)  # Rojo
            },
            'humedad': {
                'description': 'Acumulación anormal de humedad que puede indicar filtraciones',
                'severity': 'media',
                'solutions': [
                    'Identificar fuente de humedad',
                    'Mejorar ventilación del área',
                    'Aplicar selladores o impermeabilizantes'
                ],
                'color': (0, 255, 255)  # Amarillo
            },
            'corrosion': {
                'description': 'Corrosión en componentes metálicos que compromete su integridad',
                'severity': 'media',
                'solutions': [
                    'Limpiar área afectada con productos anticorrosivos',
                    'Aplicar tratamiento protector',
                    'Reemplazar piezas muy dañadas'
                ],
                'color': (0, 165, 255)  # Naranja
            },
            # ==== tus 4 clases reales ====
            'fuga_techo': {
                'description': 'Goteras o filtraciones visibles en el techo.',
                'severity': 'alta',
                'solutions': [
                    'Reparar o sellar grietas en el techo',
                    'Instalar impermeabilizante adecuado',
                    'Verificar pendientes y canaletas del techo'
                ],
                'color': (255, 0, 0)  # Rojo
            },
            'filtracion_pared': {
                'description': 'Humedad o moho visible en paredes por filtraciones de agua.',
                'severity': 'media',
                'solutions': [
                    'Detectar y corregir la fuente de humedad',
                    'Aplicar selladores o pintura impermeabilizante',
                    'Mejorar ventilación del área afectada'
                ],
                'color': (0, 255, 255)  # Amarillo
            },
            'equipo_oxidado': {
                'description': 'Componentes metálicos oxidados, especialmente en maquinaria.',
                'severity': 'media',
                'solutions': [
                    'Limpiar con removedores de óxido',
                    'Aplicar pintura anticorrosiva',
                    'Reemplazar partes muy deterioradas'
                ],
                'color': (0, 165, 255)  # Naranja
            },
            'tuberia_rota': {
                'description': 'Fuga o ruptura en tubería que puede causar daños por agua.',
                'severity': 'alta',
                'solutions': [
                    'Cerrar válvulas de paso cercanas',
                    'Reemplazar o sellar sección dañada',
                    'Revisar presión de todo el sistema'
                ],
                'color': (0, 0, 255)  # Azul
            }
        }

    # ----------------- Helpers de razonamiento ligero -----------------
    def _norm_cls(self, raw):
        if not raw:
            return "incidencia"
        s = str(raw).strip()
        s_up = s.upper().replace("_", " ")
        return ALIASES.get(s_up, s.lower())

    def _normalize_simple(self, text: str) -> str:
        """Quita acentos/ñ de forma básica para matching robusto sin dependencias externas."""
        if not text:
            return ""
        repl = (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n"))
        out = text.lower()
        for a,b in repl:
            out = out.replace(a,b)
        return out

    # --------- Descripciones dinámicas & zona inferida ---------
    def _bbox_metrics(self, bbox, img_shape):
        """Métricas normalizadas del bbox respecto al frame."""
        if not bbox or img_shape is None:
            return dict(area=0.0, x=0.5, y=0.5, w=0.0, h=0.0, ar=1.0)
        h, w = img_shape[:2]
        x1, y1, x2, y2 = bbox
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        area = (bw * bh) / float(max(1, w * h))
        cx = (x1 + x2) / 2.0 / float(max(1, w))
        cy = (y1 + y2) / 2.0 / float(max(1, h))
        ar = bw / float(max(1, bh))
        return dict(area=area, x=cx, y=cy, w=bw/float(max(1, w)), h=bh/float(max(1, h)), ar=ar)

    def _nivel_texto(self, score):
        """Mapea score 0-1 a leve/moderado/severo para texto."""
        if score >= 0.66: return "severo"
        if score >= 0.35: return "moderado"
        return "leve"

    def _parte_vertical(self, y_rel):
        if y_rel < 0.33: return "parte alta"
        if y_rel > 0.66: return "parte baja"
        return "altura media"

    def _describe_detection(self, cls, conf, bbox, zona, img_shape, multiplicidad=1):
        """
        Descripción corta y contextual del evento detectado.
        Considera clase, confianza, tamaño/posición del bbox, multiplicidad y zona.
        """
        m = self._bbox_metrics(bbox, img_shape)
        score = 0.6*float(conf) + 0.4*min(m["area"]*4.0, 1.0)  # mezcla confianza + tamaño relativo
        nivel = self._nivel_texto(score)
        parte = self._parte_vertical(m["y"])
        multi = multiplicidad > 1
        zona_sensible = any(k in (zona or "").lower() for k in ["eléctrico", "tablero", "ups", "rack", "servidor"])

        if cls == "tuberia_rota":
            trozo = "rotura de tubería"
            ext = "con fuga activa" if score >= 0.66 else "con goteo evidente" if score >= 0.35 else "con posible microfuga"
            riesgo = "; riesgo de contacto eléctrico" if zona_sensible else ""
            foco = " múltiples puntos" if multi else " un punto"
            return f"Fuga {nivel} por {trozo} en {parte}{riesgo};{foco} detectado(s) {ext}."

        if cls == "fuga_techo":
            ext = "filtración extensa" if m["area"] >= 0.08 else "goteo localizado"
            return f"{ext} en cubierta (techo), {nivel}, predominante en {parte}."

        if cls == "filtracion_pared":
            ext = "mancha de humedad amplia" if m["area"] >= 0.06 else "mancha de humedad localizada"
            dif = " con varios focos" if multi else ""
            return f"{ext}{dif} en pared ({parte}); avance {nivel}."

        if cls == "equipo_oxidado":
            ext = "corrosión avanzada" if nivel == "severo" else "corrosión moderada" if nivel == "moderado" else "signos incipientes de corrosión"
            return f"{ext} en equipo/estructura metálica; posible pérdida de integridad."

        # Fallback genérico
        base = CONCEPTOS.get(cls, f"Incidencia detectada: {cls}")
        return f"{base} (impacto {nivel}, {parte})."

    def _infer_zone(self, image_path: str, detections, img_shape=None) -> str:
        """
        Infere 'zona/lugar' automáticamente.
        1) Usa palabras clave del nombre del archivo.
        2) Usa las clases detectadas.
        3) Usa la posición vertical del bbox (si hay shape) para pared/tubería.
        """
        try:
            base = os.path.basename(image_path) if image_path else ""
            base_norm = self._normalize_simple(base)

            # 1) Palabras clave en filename
            for k, label in ZONA_KEYWORDS.items():
                k_norm = self._normalize_simple(k)
                if k_norm in base_norm:
                    return label

            # 2) & 3) Señales de detección
            H = img_shape[0] if (img_shape is not None and len(img_shape) >= 2) else None

            classes = [self._norm_cls(d.get("name") or d.get("class")) for d in (detections or [])]
            boxes   = [d.get("bbox") for d in (detections or [])]

            def mean_y_for(cls_name):
                if H is None:
                    return None
                ys = []
                for c, b in zip(classes, boxes):
                    if c == cls_name and b and len(b) == 4:
                        _, y1, _, y2 = b
                        ys.append((y1 + y2)/2.0)
                if not ys:
                    return None
                return np.mean(ys) / float(H)

            if "fuga_techo" in classes:
                return "Techo / Cubierta"

            if "filtracion_pared" in classes:
                my = mean_y_for("filtracion_pared")
                if my is not None:
                    if my < 0.33:
                        return "Pared (parte alta)"
                    elif my > 0.66:
                        return "Pared (parte baja)"
                return "Pared interior"

            if "tuberia_rota" in classes:
                my = mean_y_for("tuberia_rota")
                if "equipo_oxidado" in classes or "cable_expuesto" in classes:
                    return "Zona técnica (cercana a instalaciones)"
                if my is not None:
                    if my > 0.6:
                        return "Área de piso / canaletas"
                    elif my < 0.35:
                        return "Área alta de plomería"
                return "Área de plomería"

            if "equipo_oxidado" in classes:
                return "Cuarto de máquinas"

        except Exception as e:
            self.logger.warning(f"No se pudo inferir zona automáticamente: {str(e)}")

        return "N/D"

    def _prioridad_y_urgencia(self, cls: str, conf: float, zona: str = ""):
        zona_sensible = any(k in (zona or "").lower() for k in ["eléctrico", "servidor", "ups", "tablero", "rack"])
        if cls in CRITICAS or conf >= 0.85 or zona_sensible:
            return "Alta", "Inmediata"
        if 0.60 <= conf < 0.85:
            return "Media", "programada"
        return "Baja", "72h"

    def _acciones_recomendadas(self, cls: str, zona: str = ""):
        acciones = ACCIONES_BASE.get(cls, ["Realizar inspección detallada y levantar diagnóstico."])
        if cls == "tuberia_rota" and any(k in (zona or "").lower() for k in ["eléctrico", "tablero", "ups", "rack"]):
            acciones = ["Cortar suministro eléctrico del área"] + acciones
        return acciones

    def _categorias_trabajo(self, cls: str, zona: str = ""):
        cats = CATEGORIAS.get(cls, ["Mantenimiento"])
        if cls == "tuberia_rota" and any(k in (zona or "").lower() for k in ["eléctrico", "tablero", "ups", "rack"]):
            cats = cats + ["Electricidad"]
        seen, out = set(), []
        for c in cats:
            if c not in seen:
                seen.add(c); out.append(c)
        return out

    def _build_structured_payload(self, img_name, modelo, detections, zona="", img_shape=None):
        # detections: [{name, confidence(0-1), bbox}]
        resumen = {
            "imagen": img_name,
            "fecha": datetime.utcnow().isoformat() + "Z",
            "lugar": zona or "N/D",
            "modelo": str(modelo),
            "detecciones": len(detections)
        }

        counts = {}
        for d in detections:
            cls = self._norm_cls(d.get("name") or d.get("class"))
            counts[cls] = counts.get(cls, 0) + 1

        reporte, solucion = [], []
        for det in detections:
            cls = self._norm_cls(det.get("name") or det.get("class"))
            conf = float(det.get("confidence", 0.0))
            prioridad, urgencia = self._prioridad_y_urgencia(cls, conf, zona)
            desc = self._describe_detection(cls, conf, det.get("bbox"), zona, img_shape, counts.get(cls, 1))

            reporte.append({
                "problema": cls,
                "descripcion": desc,
                "confianza": round(conf * 100, 1),
                "prioridad": prioridad,
                "urgencia": urgencia,
                "concepto_dano": CONCEPTOS.get(cls, "Incidencia por confirmar"),
                "evidencia": {"bbox": det.get("bbox")}
            })
            solucion.append({
                "problema": cls,
                "acciones_recomendadas": self._acciones_recomendadas(cls, zona),
                "categorias_trabajo": self._categorias_trabajo(cls, zona),
                "segun_prioridad": {
                    "Alta": "Asignar cuadrilla <2h, notificar supervisor y crear OT.",
                    "Baja": "Programar en próxima ventana de mantenimiento."
                },
                "workers_detalle": {
                    "Alta": "Técnico senior + ayudante; EPP completo.",
                    "Baja": "Técnico estándar; verificación posterior."
                }
            })

        payload = {
            "resumen_inspeccion": resumen,
            "reporte_incidencia": reporte,
            "solucion": solucion
        }

        if reporte:
            top = max(reporte, key=lambda x: PRIO_RANK[x["prioridad"]])
            payload["resumen_inspeccion"]["prioridad_global"] = top["prioridad"]
            payload["resumen_inspeccion"]["urgencia_global"] = top["urgencia"]
        else:
            payload["resumen_inspeccion"]["prioridad_global"] = "Baja"
            payload["resumen_inspeccion"]["urgencia_global"] = "72h"

        acc = []
        for s in solucion:
            acc.extend(s["acciones_recomendadas"])
        seen, out = set(), []
        for a in acc:
            if a not in seen:
                seen.add(a); out.append(a)
        payload["resumen_inspeccion"]["acciones_recomendadas_globales"] = out[:6]

        return payload

    # ----------------- Método principal (con zona) -----------------
    def detect_problems(self, image_path, zona: str = ""):
        """Detección principal con manejo de errores robusto. 'zona' es opcional."""
        if not os.path.exists(image_path):
            return {'error': 'La imagen no existe en la ruta especificada'}

        try:
            img = cv2.imread(image_path)
            if img is None:
                return {'error': 'No se pudo leer la imagen, formato posiblemente no soportado'}

            results = self.model(img)
            names = getattr(self.model, "names", {})

            detections = []
            for result in results:
                for box in result.boxes:
                    try:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        class_name_raw = names.get(cls_id, str(cls_id))
                        class_name = self._norm_cls(class_name_raw)

                        problem_info = self.problem_descriptions.get(class_name, {
                            'description': f'Problema detectado: {class_name}',
                            'severity': 'desconocida',
                            'solutions': ['Contactar a un especialista para evaluación'],
                            'color': (128, 0, 128)  # Morado
                        })

                        # Dibujar detección
                        cv2.rectangle(img, (x1, y1), (x2, y2), problem_info['color'], 2)
                        label = f"{class_name} {conf:.2f}"
                        cv2.putText(img, label, (x1, y1-10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, problem_info['color'], 2)

                        detections.append({
                            'class': class_name,
                            'confidence': conf,
                            'confidence_pct': round(conf * 100, 1),
                            'box': [x1, y1, x2, y2],
                            'color': problem_info['color'],
                            'description': problem_info['description'],
                            'severity': problem_info['severity'],
                            'solutions': problem_info['solutions']
                        })
                    except Exception as e:
                        self.logger.error(f"Error procesando detección: {str(e)}")
                        continue

            # Guardar imagen procesada
            result_path = image_path.replace('uploads', 'results')
            os.makedirs(os.path.dirname(result_path), exist_ok=True)
            cv2.imwrite(result_path, img)

            # -------- Sección estructurada (Detección/Solución) --------
            det_min = [
                {"name": d["class"], "confidence": d["confidence"], "bbox": d["box"]}
                for d in detections
            ]

            zona_inferida = zona or self._infer_zone(image_path, det_min, img_shape=img.shape)

            # Actualizar descripciones dinámicas
            counts = {}
            for dm in det_min:
                c = self._norm_cls(dm["name"])
                counts[c] = counts.get(c, 0) + 1
            for d in detections:
                d['description'] = self._describe_detection(
                    d['class'], d['confidence'], d['box'], zona_inferida, img.shape, counts.get(d['class'], 1)
                )

            structured = self._build_structured_payload(
                img_name=os.path.basename(image_path),
                modelo="yolov8/pt",
                detections=det_min,
                zona=zona_inferida,
                img_shape=img.shape
            )

            return {
                'original_image': image_path,
                'processed_image': result_path,
                'detections': detections,
                'analysis': self._generate_analysis(detections),
                'maintenance_report': self._generate_maintenance_report(detections),
                'resumen_inspeccion': structured['resumen_inspeccion'],
                'reporte_incidencia': structured['reporte_incidencia'],
                'solucion': structured['solucion']
            }

        except Exception as e:
            self.logger.error(f"Error en detect_problems: {str(e)}")
            return {'error': f"Error al procesar la imagen: {str(e)}"}

    # ----------------- Estadística legacy (se mantiene) -----------------
    def _generate_analysis(self, detections):
        """Genera análisis estadístico"""
        if not detections:
            return {
                'total_problems': 0,
                'severity_distribution': {},
                'class_distribution': {},
                'average_confidence': 0
            }

        class_dist = {}
        severity_dist = {}
        total_conf = 0

        for det in detections:
            class_name = det['class']
            severity = det['severity']

            class_dist[class_name] = class_dist.get(class_name, 0) + 1
            severity_dist[severity] = severity_dist.get(severity, 0) + 1
            total_conf += det['confidence']

        return {
            'total_problems': len(detections),
            'severity_distribution': severity_dist,
            'class_distribution': class_dist,
            'average_confidence': total_conf / len(detections) if detections else 0
        }

    def _generate_maintenance_report(self, detections):
        """Genera reporte de mantenimiento con prioridades (legacy)"""
        if not detections:
            return {
                'summary': 'No se detectaron problemas en la inspección',
                'recommended_actions': ['No se requieren acciones inmediatas'],
                'priority': 'ninguna',
                'urgency': 'baja'
            }

        severities = [det['severity'] for det in detections]
        priority = 'baja'
        if 'critica' in severities:
            priority = 'crítica'
        elif 'alta' in severities:
            priority = 'alta'
        elif 'media' in severities:
            priority = 'media'

        actions = list({action for det in detections for action in det['solutions']})

        return {
            'summary': f"Inspección detectó {len(detections)} problemas ({priority})",
            'recommended_actions': actions,
            'priority': priority,
            'urgency': 'inmediata' if priority in ['crítica', 'alta'] else 'programada'
        }

    # ----------------- Método opcional (solo salida estructurada) -----------------
    def detect_structured(self, image_path: str, zona: str = "", img_name: str = None):
        """Si prefieres llamarlo directo desde app.py para solo la salida estructurada"""
        if not os.path.exists(image_path):
            return {'error': 'La imagen no existe en la ruta especificada'}
        img = cv2.imread(image_path)
        if img is None:
            return {'error': 'No se pudo leer la imagen, formato posiblemente no soportado'}
        results = self.model(img)
        names = getattr(self.model, "names", {})
        detections = []
        for r in results:
            for b in r.boxes:
                cls_id = int(b.cls[0])
                name_raw = names.get(cls_id, str(cls_id))
                name = self._norm_cls(name_raw)
                conf = float(b.conf[0])
                x1, y1, x2, y2 = map(int, b.xyxy[0])
                detections.append({"name": name, "confidence": conf, "bbox": [x1, y1, x2, y2]})

        zona_inferida = zona or self._infer_zone(image_path, detections, img_shape=img.shape)

        payload = self._build_structured_payload(
            img_name=img_name or os.path.basename(image_path),
            modelo="yolov8/pt",
            detections=detections,
            zona=zona_inferida,
            img_shape=img.shape
        )
        return payload
