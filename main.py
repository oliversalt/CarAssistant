import os
import io
import time
import wave
import json
import pyaudio
from openai import OpenAI
from anthropic import Anthropic
from elevenlabs import ElevenLabs
from dotenv import load_dotenv
from pydub import AudioSegment
from pydub.playback import play

from tools import TOOLS_ANTHROPIC as TOOLS, dispatch

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

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 512
MAX_HISTORY_TURNS = 20  # keep last 20 exchanges before trimming

SYSTEM_PROMPT = (
    "You are a knowledgeable and curious companion riding along in the car. "
    "Your job is to have real conversations — answer questions, explain ideas, discuss topics, "
    "and help the driver learn and think. You can cover anything: science, history, news, "
    "philosophy, technology, sport, music, or whatever comes up. "
    "When you need up-to-date or specific information you don't know, use the search tool. "
    "Keep every response concise and conversational — no markdown, no bullet points, no lists. "
    "Speak in complete natural sentences as if talking to a passenger. "
    "Aim for responses that take about 10 to 20 seconds to say aloud."
)


def record_audio() -> bool:
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

    with wave.open("input.wav", "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pyaudio.PyAudio().get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))
    print("✅ Recorded")
    return True


def transcribe() -> str:
    print("💬 Transcribing...")
    with open("input.wav", "rb") as f:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )
    text = transcript.text.strip()
    print(f"✅ You said: {text}")
    return text


def get_response(conversation_history: list) -> str:
    print("🤖 Thinking...")

    messages = conversation_history.copy()

    # Agentic loop — Claude may call the search tool before giving a final answer
    while True:
        response = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        # If Claude wants to use a tool
        if response.stop_reason == "tool_use":
            # Add Claude's response (with tool call) to messages
            messages.append({"role": "assistant", "content": response.content})

            # Process each tool call
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = dispatch(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})

        else:
            # Final text response
            reply = next(
                (block.text for block in response.content if hasattr(block, "text")),
                ""
            )
            print(f"✅ Claude: {reply}")
            return reply


def speak(text: str):
    print("🔊 Generating audio...")
    t0 = time.perf_counter()
    audio = elevenlabs_client.text_to_speech.convert(
        voice_id="JBFqnCBsd6RMkjVDRZzb",
        model_id="eleven_flash_v2_5",
        text=text,
    )
    audio_bytes = b"".join(audio)
    segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
    t1 = time.perf_counter()
    print(f"⏱  TTS generation: {t1 - t0:.2f}s")
    print("🔊 Playing...")
    play(segment)
    print("✅ Done speaking")


def trim_history(history: list) -> list:
    # Keep the last MAX_HISTORY_TURNS * 2 messages (each turn = user + assistant)
    max_messages = MAX_HISTORY_TURNS * 2
    if len(history) > max_messages:
        history = history[-max_messages:]
    return history


def main():
    print("=" * 50)
    print("🚗 CarPi Assistant — ready")
    print("Press Enter to start recording, or type 'quit' to exit.")
    print("=" * 50)

    conversation_history = []

    while True:
        user_input = input("\n> Press Enter to speak (or type 'quit'): ").strip().lower()
        if user_input == "quit":
            print("👋 Goodbye!")
            break

        # Record and transcribe
        record_audio()
        t0 = time.perf_counter()
        text = transcribe()
        t1 = time.perf_counter()
        print(f"⏱  Transcription: {t1 - t0:.2f}s")

        if not text:
            print("⚠️ Nothing detected, try again")
            continue

        # Add user message to history
        conversation_history.append({"role": "user", "content": text})

        # Get Claude's response (with optional tool use)
        t2 = time.perf_counter()
        reply = get_response(conversation_history)
        t3 = time.perf_counter()
        print(f"⏱  LLM response:  {t3 - t2:.2f}s")

        if not reply:
            print("⚠️ No response from Claude")
            conversation_history.pop()  # remove the unanswered user message
            continue

        # Add assistant reply to history
        conversation_history.append({"role": "assistant", "content": reply})
        conversation_history = trim_history(conversation_history)

        # Speak the reply
        t4 = time.perf_counter()
        speak(reply)
        t5 = time.perf_counter()
        print(f"⏱  TTS + playback: {t5 - t4:.2f}s")
        print(f"⏱  Total pipeline: {t5 - t0:.2f}s")


if __name__ == "__main__":
    main()
