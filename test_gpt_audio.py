import base64
import time
import wave
import pyaudio
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

MIC_INDEX = 1
DURATION = 5
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024


def record_audio(filename="input.wav"):
    print("🎤 Recording for 5 seconds... speak now!")
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

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pyaudio.PyAudio().get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))
    print("✅ Recorded")
    return filename


def ask_gpt_with_audio(filename: str) -> str:
    print("🤖 Sending audio to GPT...")
    with open(filename, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model="gpt-audio-mini-2025-12-15",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64,
                            "format": "wav"
                        }
                    }
                ]
            }
        ]
    )

    t1 = time.perf_counter()
    reply = response.choices[0].message.content
    print(f"✅ GPT: {reply}")
    print(f"⏱  Response time: {t1 - t0:.2f}s")
    return reply


record_audio()
ask_gpt_with_audio("input.wav")
