import httpx
import tempfile
from typing import Optional

from core.settings import HEYOO_TOKEN, OPENAI_API_KEY
from core.logger import LoggerManager

class AudioProcessor:
    """Service class for handling WhatsApp audio messages and transcription."""
    
    def __init__(self):
        """Initialize the audio processor with required configurations."""
        self.log = LoggerManager(name="audio_processor", level="INFO", log_to_file=False).get_logger()
        self.http_timeout = 60.0
        self.whisper_model = "whisper-1"
        self.whatsapp_api_version = "v18.0"

    async def _make_http_request(
        self, 
        url: str, 
        method: str = "GET", 
        headers: Optional[dict] = None, 
        files: Optional[dict] = None,
        data: Optional[dict] = None
    ) -> httpx.Response:
        """Make an HTTP request with timeout handling."""
        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                files=files,
                data=data
            )
            response.raise_for_status()
            return response

    async def download_audio_from_whatsapp(self, media_id: str) -> Optional[bytes]:
        """Download an audio file from WhatsApp API using the media ID."""
        try:
            # Get download URL
            headers = {"Authorization": f"Bearer {HEYOO_TOKEN}"}
            media_response = await self._make_http_request(
                f"https://graph.facebook.com/{self.whatsapp_api_version}/{media_id}",
                headers=headers
            )
            media_url = media_response.json()["url"]
            self.log.info("🎯 Audio URL obtained successfully")

            # Download actual audio file
            audio_response = await self._make_http_request(
                media_url,
                headers=headers
            )
            self.log.info("✅ Audio downloaded successfully")
            return audio_response.content

        except httpx.HTTPStatusError as e:
            self.log.error(f"❌ HTTP error downloading audio: {e.response.status_code}")
            return None
        except Exception as e:
            self.log.error(f"❌ Error downloading audio: {str(e)}")
            return None

    async def transcribe_audio_with_whisper(self, audio_bytes: bytes) -> str:
        """Send audio to OpenAI Whisper API for transcription."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".ogg") as temp_audio:
                temp_audio.write(audio_bytes)
                temp_audio.seek(0)

                files = {'file': (temp_audio.name, temp_audio.read(), 'audio/ogg')}
                data = {
                    'model': self.whisper_model,
                    'response_format': 'text'
                }
                headers = {'Authorization': f"Bearer {OPENAI_API_KEY}"}

                response = await self._make_http_request(
                    "https://api.openai.com/v1/audio/transcriptions",
                    method="POST",
                    headers=headers,
                    files=files,
                    data=data
                )

                transcription = response.text.strip()
                self.log.info("✅ Transcription received successfully")
                return transcription

        except httpx.HTTPStatusError as e:
            self.log.error(f"❌ HTTP error transcribing audio: {e.response.status_code}")
            return "No se pudo transcribir el audio debido a un error de comunicación."
        except Exception as e:
            self.log.error(f"❌ Error transcribing audio: {str(e)}")
            return "No se pudo transcribir el audio."

    async def process_audio_message(self, media_id: str) -> str:
        """Complete flow: download audio, transcribe it and return the text."""
        audio_data = await self.download_audio_from_whatsapp(media_id)
        if not audio_data:
            return "No se pudo obtener el audio del mensaje."

        return await self.transcribe_audio_with_whisper(audio_data)

# Create a singleton instance
audio_processor = AudioProcessor()
