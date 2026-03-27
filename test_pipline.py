import os
import io
import time
import pyaudio
import wave
from openai import OpenAI
from anthropic import Anthropic
from elevenlabs import ElevenLabs
from dotenv import load_dotenv
from pydub import AudioSegment
from pydub.playback import play

load_dotenv()

openai_client = OpenAI()
anthropic_client = Anthropic()
elevenlabs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

MIC_INDEX = 1
DURATION = 5
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024

def record_audio():
    print("\n🎤 Recording for 5 seconds... speak now!")
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, input_device_index=MIC_INDEX,
                    frames_per_buffer=CHUNK)
    frames = []
    for _ in range(0, int(RATE / CHUNK * DURATION)):
        frames.append(stream.read(CHUNK))
    stream.stop_stream()
    stream.close()
    p.terminate()

    with wave.open("input.wav", 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pyaudio.PyAudio().get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
    print("✅ Recorded")

def transcribe():
    print("💬 Transcribing...")
    with open("input.wav", "rb") as f:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )
    print(f"✅ You said: {transcript.text}")
    return transcript.text

def get_response(text):
    print("🤖 Thinking...")
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system="You are a helpful car assistant. Keep responses concise and conversational. No markdown, no bullet points. Speak naturally as if talking to someone driving.",
        messages=[{"role": "user", "content": text}]
    )
    reply = response.content[0].text
    print(f"✅ Claude: {reply}")
    return reply

def speak(text):
    print("🔊 Generating audio...")
    tts_start = time.perf_counter()
    audio = elevenlabs_client.text_to_speech.convert(
        voice_id="JBFqnCBsd6RMkjVDRZzb",
        model_id="eleven_flash_v2_5",
        text=text,
    )
    audio_bytes = b"".join(audio)
    segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
    tts_ready = time.perf_counter()
    print(f"⏱    TTS generation: {tts_ready - tts_start:.2f}s")
    print("🔊 Playing...")
    play(segment)
    print("✅ Done")

# --- Run the pipeline ---
record_audio()
_pipeline_start = time.perf_counter()

t0 = time.perf_counter()
text = transcribe()
t1 = time.perf_counter()
print(f"⏱  Transcription:  {t1 - t0:.2f}s")

if text.strip():
    t2 = time.perf_counter()
    response = get_response(text)
    t3 = time.perf_counter()
    print(f"⏱  LLM response:   {t3 - t2:.2f}s")

    t4 = time.perf_counter()
    speak(response)
    t5 = time.perf_counter()
    print(f"⏱  TTS + playback: {t5 - t4:.2f}s")
    print(f"⏱  Total:          {t5 - _pipeline_start:.2f}s")
else:
    print("⚠️ Nothing detected, try again")