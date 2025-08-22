import os
from PIL import Image
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\rcondet\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
import PyPDF2
from typing import Union

def process_uploaded_file(file_path: str) -> Union[str, dict]:
    file_ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if file_ext in ['.jpg', '.jpeg', '.png']:
            # Procesamiento de imágenes
            text = pytesseract.image_to_string(Image.open(file_path))
            return {"type": "image", "text": text}
        
        elif file_ext == '.pdf':
            # Procesamiento de PDF
            text = ""
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    text += page.extract_text()
            return {"type": "pdf", "text": text}
        
        elif file_ext in ['.txt', '.docx']:
            # Procesamiento de texto
            with open(file_path, 'r', encoding='utf-8') as file:
                return {"type": "text", "content": file.read()}
    
    except Exception as e:
        return {"error": str(e)}