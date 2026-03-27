import os
import io
from elevenlabs import ElevenLabs
from dotenv import load_dotenv
from pydub import AudioSegment
from pydub.playback import play

load_dotenv()

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

text = "I'm your car assistant, ready to help you on the road."

print("Sending to ElevenLabs...")

audio = client.text_to_speech.convert(
    voice_id="JBFqnCBsd6RMkjVDRZzb",
    model_id="eleven_flash_v2_5",
    text=text,
)

audio_bytes = b"".join(audio)

print("Playing back...")

segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
play(segment)

print("Done!")