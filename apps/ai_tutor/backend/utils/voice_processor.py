import speech_recognition as sr
from gtts import gTTS
import os
import uuid
from pydub import AudioSegment
from pathlib import Path

class VoiceProcessor:
    def __init__(self):
        self.recognizer = sr.Recognizer()

        # Base absoluta de la subapp (este archivo está en .../apps/ai_tutor/backend/utils/)
        # parents[2] -> .../apps/ai_tutor
        self._base = Path(__file__).resolve().parents[2]

        # static/audio absoluto y creación con padres
        self.audio_dir = self._base / "static" / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, p: str) -> Path:
        """Resuelve rutas tipo '/static/...' o 'static/...' a la ubicación real en disco."""
        pth = Path(p)
        if pth.is_file():
            return pth
        if str(p).startswith("/static/"):
            return self._base / str(p).lstrip("/")
        if str(p).startswith("static/"):
            return self._base / p
        return pth

    def speech_to_text(self, audio_path: str) -> str:
        try:
            src = self._resolve_path(audio_path)
            with sr.AudioFile(str(src)) as source:
                audio = self.recognizer.record(source)
                return self.recognizer.recognize_google(audio, language='es-ES')
        except Exception as e:
            print(f"Error en speech_to_text: {e}")
            return ""

    def text_to_speech(self, text: str) -> str:
        try:
            # Generar nombre único para el archivo MP3
            mp3_path = self.audio_dir / f"response_{uuid.uuid4()}.mp3"

            # Convertir texto a voz (es-ES -> 'es' para gTTS)
            tts = gTTS(text=text, lang='es', slow=False)
            tts.save(str(mp3_path))

            # Intentar convertir a OGG (si ffmpeg no está, devolvemos MP3)
            try:
                ogg_path = mp3_path.with_suffix('.ogg')
                sound = AudioSegment.from_mp3(str(mp3_path))
                sound.export(str(ogg_path), format='ogg')
                return f"/static/audio/{ogg_path.name}"
            except Exception as conv_err:
                print(f"Aviso: no se pudo convertir a OGG ({conv_err}). Se usará MP3.")
                return f"/static/audio/{mp3_path.name}"

        except Exception as e:
            print(f"Error en text_to_speech: {e}")
            return ""
