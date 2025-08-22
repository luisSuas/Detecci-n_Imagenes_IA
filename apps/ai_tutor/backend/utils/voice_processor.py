import speech_recognition as sr
from gtts import gTTS
import os
import uuid
from pydub import AudioSegment
from pathlib import Path

class VoiceProcessor:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.audio_dir = Path("static/audio")
        self.audio_dir.mkdir(exist_ok=True)
    
    def speech_to_text(self, audio_path: str) -> str:
        try:
            with sr.AudioFile(audio_path) as source:
                audio = self.recognizer.record(source)
                return self.recognizer.recognize_google(audio, language='es-ES')
        except Exception as e:
            print(f"Error en speech_to_text: {e}")
            return ""
    
    def text_to_speech(self, text: str) -> str:
        try:
            # Generar nombre único para el archivo
            audio_path = self.audio_dir / f"response_{uuid.uuid4()}.mp3"
            
            # Convertir texto a voz
            tts = gTTS(text=text, lang='es', slow=False)
            tts.save(str(audio_path))
            
            # Convertir a formato web compatible
            sound = AudioSegment.from_mp3(str(audio_path))
            ogg_path = audio_path.with_suffix('.ogg')
            sound.export(str(ogg_path), format='ogg')
            
            return f"/static/audio/{ogg_path.name}"
            
        except Exception as e:
            print(f"Error en text_to_speech: {e}")
            return ""