import cv2
import numpy as np
from ultralytics import YOLO
from PIL import Image
import os

class ObjectDetector:
    def __init__(self, model_path='yolov8n.pt'):
        """Inicializa el modelo YOLO"""
        self.model = YOLO(model_path)
        self.class_names = self.model.names
    
    def detect_objects(self, image_path):
        """Realiza la detección de objetos en una imagen"""
        # Leer la imagen
        img = cv2.imread(image_path)
        original_img = img.copy()
        
        # Realizar la detección
        results = self.model(img)
        
        # Procesar resultados
        detections = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                class_name = self.class_names[cls]
                
                # Dibujar el cuadro y etiqueta
                color = self._get_color(cls)
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                label = f"{class_name} {conf:.2f}"
                cv2.putText(img, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
                # Guardar detección
                detections.append({
                    'class': class_name,
                    'confidence': conf,
                    'box': [x1, y1, x2, y2],
                    'color': color
                })
        
        # Guardar imagen con detecciones
        result_path = image_path.replace('uploads', 'results')
        cv2.imwrite(result_path, img)
        
        # Generar análisis general
        analysis = self._generate_analysis(detections)
        
        return {
            'original_image': image_path,
            'processed_image': result_path,
            'detections': detections,
            'analysis': analysis
        }
    
    def _get_color(self, class_id):
        """Genera un color único para cada clase"""
        np.random.seed(class_id)
        return tuple(map(int, np.random.randint(0, 255, 3)))
    
    def _generate_analysis(self, detections):
        """Genera un análisis estadístico de las detecciones"""
        if not detections:
            return {
                'total_objects': 0,
                'class_distribution': {},
                'average_confidence': 0
            }
        
        class_dist = {}
        total_conf = 0
        
        for det in detections:
            class_name = det['class']
            class_dist[class_name] = class_dist.get(class_name, 0) + 1
            total_conf += det['confidence']
        
        return {
            'total_objects': len(detections),
            'class_distribution': class_dist,
            'average_confidence': total_conf / len(detections)
        }