from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

print("Sending to Whisper...")

with open("test.wav", "rb") as f:
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=f
    )

print("Transcription:", transcript.text)