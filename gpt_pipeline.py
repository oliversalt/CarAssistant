"""
GPT Audio Pipeline
------------------
Uses gpt-audio-mini-2025-12-15 for audio-in / text-out (or audio-out).
Supports web search via tool use.
Two output modes:
  - elevenlabs  : GPT returns text, ElevenLabs speaks it (default)
  - gpt         : GPT returns audio directly, played back via PyAudio

Usage:
    python gpt_pipeline.py              # ElevenLabs TTS mode
    python gpt_pipeline.py --voice gpt  # GPT native audio output mode
"""

import argparse
import base64
import io
import json
import os
import time
import wave

import pyaudio
from dotenv import load_dotenv
from ddgs import DDGS
from elevenlabs import ElevenLabs
from openai import OpenAI
from pydub import AudioSegment
from pydub.playback import play

load_dotenv()

openai_client = OpenAI()
elevenlabs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

MIC_INDEX = 1
DURATION = 5
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024

MODEL = "gpt-audio-mini-2025-12-15"
MAX_HISTORY_TURNS = 20

ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
ELEVENLABS_MODEL = "eleven_flash_v2_5"
GPT_VOICE = "alloy"  # options: alloy, echo, fable, onyx, nova, shimmer

SYSTEM_PROMPT = (
    "You are a knowledgeable and curious companion riding along in the car. "
    "Your job is to have real conversations — answer questions, explain ideas, discuss topics, "
    "and help the driver learn and think about the world. You can talk about anything: "
    "science, history, current events, philosophy, technology, sport, music, culture, or whatever "
    "the driver brings up. You have access to a web search tool — use it whenever a question "
    "would benefit from up-to-date information, recent news, or specific facts you're unsure about. "
    "Keep every response concise and conversational. No markdown, no bullet points, no lists. "
    "Speak in complete natural sentences as if talking to a passenger next to you. "
    "Aim for responses that take about 10 to 20 seconds to say aloud."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the internet for current information, news, facts, or anything you are "
                "uncertain about or that may have changed since your training. Use this whenever "
                "the user asks about recent events, current prices, live scores, or anything "
                "that benefits from up-to-date information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up."
                    }
                },
                "required": ["query"]
            }
        }
    }
]


def web_search(query: str) -> str:
    print(f"🔍 Searching: {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return "No results found."
        return "\n\n".join(f"{r['title']}: {r['body']}" for r in results)
    except Exception as e:
        return f"Search failed: {e}"


def record_audio(filename="input.wav"):
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

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pyaudio.PyAudio().get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))
    print("✅ Recorded")
    return filename


def encode_audio(filename: str) -> str:
    with open(filename, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_response(conversation_history: list, audio_b64: str, voice_mode: str) -> tuple[str, bytes | None]:
    """
    Send audio + conversation history to GPT.
    Returns (reply_text, audio_bytes_or_None).
    audio_bytes is only set when voice_mode == 'gpt'.
    """
    modalities = ["text", "audio"] if voice_mode == "gpt" else ["text"]
    audio_config = {"voice": GPT_VOICE, "format": "wav"} if voice_mode == "gpt" else None

    # Build the new user message with audio
    user_message = {
        "role": "user",
        "content": [
            {
                "type": "input_audio",
                "input_audio": {"data": audio_b64, "format": "wav"}
            }
        ]
    }

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history + [user_message]

    # Agentic loop — GPT may call web_search before answering
    while True:
        kwargs = dict(
            model=MODEL,
            modalities=modalities,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        if audio_config:
            kwargs["audio"] = audio_config

        t0 = time.perf_counter()
        response = openai_client.chat.completions.create(**kwargs)
        t1 = time.perf_counter()

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls":
            tool_calls = choice.message.tool_calls
            # Add assistant message with tool calls to context
            messages.append(choice.message)

            for tc in tool_calls:
                args = json.loads(tc.function.arguments)
                result = web_search(args["query"])
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result
                })
        else:
            print(f"⏱  GPT response: {t1 - t0:.2f}s")

            reply_text = choice.message.content or ""

            # In audio mode the text transcript comes from the audio object
            audio_bytes = None
            if voice_mode == "gpt" and choice.message.audio:
                audio_data = choice.message.audio.data
                audio_bytes = base64.b64decode(audio_data)
                if not reply_text:
                    reply_text = choice.message.audio.transcript or ""

            print(f"✅ GPT: {reply_text}")
            return reply_text, audio_bytes


def speak_elevenlabs(text: str):
    print("🔊 Generating ElevenLabs audio...")
    t0 = time.perf_counter()
    audio = elevenlabs_client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        model_id=ELEVENLABS_MODEL,
        text=text,
    )
    audio_bytes = b"".join(audio)
    segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
    t1 = time.perf_counter()
    print(f"⏱  TTS generation: {t1 - t0:.2f}s")
    print("🔊 Playing...")
    play(segment)
    print("✅ Done speaking")


def speak_gpt_audio(audio_bytes: bytes):
    print("🔊 Playing GPT audio...")
    t0 = time.perf_counter()
    segment = AudioSegment.from_wav(io.BytesIO(audio_bytes))
    play(segment)
    t1 = time.perf_counter()
    print(f"⏱  Playback: {t1 - t0:.2f}s")
    print("✅ Done speaking")


def trim_history(history: list) -> list:
    max_messages = MAX_HISTORY_TURNS * 2
    return history[-max_messages:] if len(history) > max_messages else history


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--voice", choices=["elevenlabs", "gpt"], default="elevenlabs",
        help="Output mode: 'elevenlabs' (default) or 'gpt' for native GPT audio"
    )
    args = parser.parse_args()

    print("=" * 50)
    print(f"🚗 CarPi — GPT Audio Pipeline")
    print(f"🔊 Voice mode: {args.voice}")
    print("Press Enter to speak, or type 'quit' to exit.")
    print("=" * 50)

    conversation_history = []

    while True:
        user_input = input("\n> Press Enter to speak (or type 'quit'): ").strip().lower()
        if user_input == "quit":
            print("👋 Goodbye!")
            break

        t_start = time.perf_counter()

        record_audio()
        audio_b64 = encode_audio("input.wav")

        reply_text, audio_bytes = get_response(conversation_history, audio_b64, args.voice)

        if not reply_text and not audio_bytes:
            print("⚠️ No response received, try again")
            continue

        # Store transcript in history as plain text turns
        # For audio input we store the transcript GPT saw; for the reply we store the text
        conversation_history.append({
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {"data": audio_b64, "format": "wav"}
                }
            ]
        })
        if reply_text:
            conversation_history.append({"role": "assistant", "content": reply_text})
        conversation_history = trim_history(conversation_history)

        # Speak the response
        t_speak = time.perf_counter()
        if args.voice == "gpt" and audio_bytes:
            speak_gpt_audio(audio_bytes)
        else:
            speak_elevenlabs(reply_text)
        t_end = time.perf_counter()

        print(f"⏱  TTS + playback: {t_end - t_speak:.2f}s")
        print(f"⏱  Total pipeline: {t_end - t_start:.2f}s")


if __name__ == "__main__":
    main()
