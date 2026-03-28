"""
Realtime Pipeline — gpt-realtime-1.5
-------------------------------------
Uses the OpenAI Realtime API over a persistent WebSocket.
Push-to-talk: press Enter to start speaking, press Enter again to stop.
The WebSocket stays open between turns — no reconnection delay.
Prints a full conversation transcript when you quit.

Usage:
    python realtime_pipeline.py
"""

import asyncio
import base64
import json
import os
import queue
import threading
import time

import pyaudio
import websockets
from dotenv import load_dotenv

load_dotenv()

MIC_INDEX = 1
RATE = 24000        # Realtime API expects 24kHz PCM16
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024

MODEL = "gpt-realtime-1.5"
VOICE = "alloy"     # options: alloy, echo, fable, onyx, nova, shimmer
WS_URL = f"wss://api.openai.com/v1/realtime?model={MODEL}"

SYSTEM_PROMPT = (
    "You are a knowledgeable and curious companion riding along in the car. "
    "Your job is to have real conversations — answer questions, explain ideas, discuss topics, "
    "and help the driver learn and think about the world. You can talk about anything: "
    "science, history, current events, philosophy, technology, sport, music, culture, or "
    "whatever the driver brings up. "
    "Keep every response concise and conversational. Speak in complete natural sentences "
    "as if talking to a passenger next to you. "
    "Aim for responses that take about 10 to 20 seconds to say aloud."
)


# ---------------------------------------------------------------------------
# Audio playback — runs in its own thread, plays PCM16 chunks from a queue
# ---------------------------------------------------------------------------

def audio_player(play_queue: queue.Queue):
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True)
    try:
        while True:
            chunk = play_queue.get()
            if chunk is None:   # sentinel — stop playing
                break
            stream.write(chunk)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


# ---------------------------------------------------------------------------
# Mic streaming — async task, sends audio chunks over the WebSocket
# ---------------------------------------------------------------------------

async def stream_mic(ws, stop_event: asyncio.Event):
    loop = asyncio.get_event_loop()
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, input_device_index=MIC_INDEX,
                    frames_per_buffer=CHUNK)
    try:
        while not stop_event.is_set():
            data = await loop.run_in_executor(None, stream.read, CHUNK)
            b64 = base64.b64encode(data).decode()
            await ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": b64
            }))
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


# ---------------------------------------------------------------------------
# Response receiver — reads WebSocket events until response.done
# ---------------------------------------------------------------------------

async def receive_response(ws, play_queue: queue.Queue, t_committed: float) -> tuple[str, str]:
    """
    Consumes WebSocket events for one response turn.
    Plays audio via play_queue as chunks arrive.
    Returns (user_transcript, assistant_transcript).
    """
    user_text = ""
    assistant_text = ""
    t_first_audio = None

    async for raw in ws:
        event = json.loads(raw)
        etype = event.get("type", "")

        if etype == "response.audio.delta":
            if t_first_audio is None:
                t_first_audio = time.perf_counter()
                print(f"⏱  Commit → first audio:    {t_first_audio - t_committed:.2f}s")
            play_queue.put(base64.b64decode(event["delta"]))

        elif etype == "response.audio_transcript.delta":
            assistant_text += event.get("delta", "")

        elif etype == "conversation.item.input_audio_transcription.completed":
            user_text = event.get("transcript", "").strip()
            print(f"💬 You said: {user_text}")

        elif etype == "response.done":
            t_done = time.perf_counter()
            print(f"⏱  Commit → response done:  {t_done - t_committed:.2f}s")
            break

        elif etype == "error":
            print(f"⚠️  API error: {event.get('error', event)}")
            break

    play_queue.put(None)  # tell player thread to stop
    return user_text, assistant_text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1",
    }

    print("=" * 50)
    print("🚗 CarPi — Realtime Pipeline")
    print(f"   Model: {MODEL}  |  Voice: {VOICE}")
    print("   Press Enter to start speaking.")
    print("   Press Enter again to stop and get a response.")
    print("   Type 'quit' then Enter to exit.")
    print("=" * 50)

    conversation_log = []   # {"role": "user"/"assistant", "text": "..."}
    loop = asyncio.get_event_loop()

    async with websockets.connect(WS_URL, additional_headers=headers) as ws:

        # --- Handshake ---
        raw = await ws.recv()
        event = json.loads(raw)
        if event.get("type") != "session.created":
            print(f"⚠️  Unexpected first event: {event.get('type')}")
            return
        print("✅ Session created")

        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": SYSTEM_PROMPT,
                "voice": VOICE,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": None,     # manual push-to-talk
            }
        }))

        raw = await ws.recv()
        if json.loads(raw).get("type") == "session.updated":
            print("✅ Session configured — ready\n")

        # --- Conversation loop ---
        while True:
            user_input = await loop.run_in_executor(
                None, input, "> Press Enter to speak (or type 'quit'): "
            )
            if user_input.strip().lower() == "quit":
                break

            # Recording phase
            print("🎤 Recording... press Enter to stop")
            t_record_start = time.perf_counter()
            stop_recording = asyncio.Event()
            mic_task = asyncio.create_task(stream_mic(ws, stop_recording))

            await loop.run_in_executor(None, input, "")   # blocks until Enter
            stop_recording.set()
            await mic_task

            t_record_end = time.perf_counter()
            print(f"⏱  Recording duration:      {t_record_end - t_record_start:.2f}s")

            # Commit audio and request a response
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            await ws.send(json.dumps({"type": "response.create"}))
            t_committed = time.perf_counter()

            # Start audio player thread
            play_queue: queue.Queue = queue.Queue()
            player = threading.Thread(target=audio_player, args=(play_queue,), daemon=True)
            player.start()

            # Receive response (plays audio as it arrives)
            print("🤖 Thinking...")
            user_text, assistant_text = await receive_response(ws, play_queue, t_committed)

            player.join()   # wait for all audio to finish playing
            t_playback_end = time.perf_counter()
            print(f"⏱  Commit → playback end:   {t_playback_end - t_committed:.2f}s")
            print(f"✅ Assistant: {assistant_text}\n")

            if user_text:
                conversation_log.append({"role": "user", "text": user_text})
            if assistant_text:
                conversation_log.append({"role": "assistant", "text": assistant_text})

    # --- Transcript ---
    if conversation_log:
        print("\n" + "=" * 50)
        print("📝 Conversation Transcript")
        print("=" * 50)
        for entry in conversation_log:
            label = "You" if entry["role"] == "user" else "Assistant"
            print(f"\n{label}:\n  {entry['text']}")
        print("\n" + "=" * 50)
    else:
        print("\n(No conversation recorded)")


if __name__ == "__main__":
    asyncio.run(main())
