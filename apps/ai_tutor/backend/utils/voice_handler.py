import speech_recognition as sr
from gtts import gTTS
import os
from pydub import AudioSegment
from fastapi import UploadFile

# Configuración del reconocedor de voz
recognizer = sr.Recognizer()

async def speech_to_text(audio_file: UploadFile):
    try:
        with sr.AudioFile(audio_file.file) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language='es-ES')
            return text
    except Exception as e:
        print(f"Error en speech_to_text: {e}")
        return ""

def text_to_speech(text: str, lang='es'):
    tts = gTTS(text=text, lang=lang, slow=False)
    audio_path = "temp_audio.mp3"
    tts.save(audio_path)
    
    # Convertir a formato web compatible
    sound = AudioSegment.from_mp3(audio_path)
    sound.export("static/audio/output.ogg", format="ogg")
    return "static/audio/output.ogg"