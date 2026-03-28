"""
Realtime Pipeline — gpt-realtime-1.5
-------------------------------------
Uses the OpenAI Realtime API over a persistent WebSocket.
Push-to-talk: press Enter to start speaking, press Enter again to stop.
Press Enter while the model is speaking to interrupt it and start talking.
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

from tools import TOOLS, dispatch

load_dotenv()

MIC_INDEX = 1
RATE = 24000        # Realtime API expects 24kHz PCM16
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024

MODEL = "gpt-realtime-1.5"
VOICE = "alloy"     # options: alloy, echo, fable, onyx, nova, shimmer
WS_URL = f"wss://api.openai.com/v1/realtime?model={MODEL}"

def get_input(prompt=""):
    result = input(prompt)
    print("⌨️  Enter pressed")
    return result


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

def audio_player(play_queue: queue.Queue, stop_event: threading.Event):
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True)
    try:
        while not stop_event.is_set():
            chunk = play_queue.get()
            if chunk is None:   # sentinel — stop playing
                break
            stream.write(chunk)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


def drain_queue(q: queue.Queue):
    """Empty a queue and send the None sentinel to stop the player thread."""
    while not q.empty():
        try:
            q.get_nowait()
        except queue.Empty:
            break
    q.put(None)


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

async def receive_response(
    ws,
    play_queue: queue.Queue,
    t_committed: float,
    interrupt_event: asyncio.Event,
) -> tuple[str, str, bool]:
    """
    Consumes WebSocket events for one response turn.
    Handles tool calls before the final audio response.
    Plays audio via play_queue as chunks arrive.

    Returns (user_transcript, assistant_transcript, was_interrupted).
    """
    user_text = ""
    assistant_text = ""
    t_first_audio = None
    pending_fn_calls: dict[str, dict] = {}   # call_id → {name, arguments}

    async for raw in ws:
        # Check for interrupt on every event
        if interrupt_event.is_set():
            await ws.send(json.dumps({"type": "response.cancel"}))
            drain_queue(play_queue)
            # Drain stale WebSocket events until the server confirms the cancel.
            # Without this, leftover audio.delta events from the cancelled response
            # sit in the buffer and get picked up as the next response's audio.
            print("🧹 Draining cancelled response...")
            async for stale in ws:
                stale_type = json.loads(stale).get("type", "")
                if stale_type in ("response.cancelled", "response.done", "error"):
                    print(f"✅ Cancel confirmed ({stale_type})")
                    break
            return user_text, assistant_text, True

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

        elif etype == "response.output_item.added":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                pending_fn_calls[item["call_id"]] = {"name": item["name"], "arguments": ""}

        elif etype == "response.function_call_arguments.delta":
            call_id = event.get("call_id")
            if call_id in pending_fn_calls:
                pending_fn_calls[call_id]["arguments"] += event.get("delta", "")

        elif etype == "response.done":
            t_done = time.perf_counter()
            print(f"⏱  Commit → response done:  {t_done - t_committed:.2f}s")

            if pending_fn_calls:
                for call_id, fn in pending_fn_calls.items():
                    args = json.loads(fn["arguments"])
                    result = dispatch(fn["name"], args)
                    await ws.send(json.dumps({
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": result,
                        }
                    }))
                pending_fn_calls.clear()
                await ws.send(json.dumps({"type": "response.create"}))
                t_committed = time.perf_counter()
            else:
                break

        elif etype == "error":
            print(f"⚠️  API error: {event.get('error', event)}")
            break

    play_queue.put(None)
    return user_text, assistant_text, False


# ---------------------------------------------------------------------------
# Recording phase — shared between normal turns and post-interrupt turns
# ---------------------------------------------------------------------------

async def do_recording(ws, loop) -> float:
    """
    Records mic audio and sends it to the WebSocket.
    Returns t_record_end (perf_counter at the moment recording stops).
    """
    print("🎤 Recording... press Enter to stop")
    t_record_start = time.perf_counter()
    stop_recording = asyncio.Event()
    mic_task = asyncio.create_task(stream_mic(ws, stop_recording))

    await loop.run_in_executor(None, get_input)
    print("⏹  Recording stopped")
    stop_recording.set()
    await mic_task

    t_record_end = time.perf_counter()
    print(f"⏱  Recording duration:      {t_record_end - t_record_start:.2f}s")
    return t_record_end


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
    print("   Press Enter while the model is speaking to interrupt it.")
    print("   Type 'quit' then Enter to exit.")
    print("=" * 50)

    conversation_log = []
    loop = asyncio.get_event_loop()

    async with websockets.connect(WS_URL, additional_headers=headers) as ws:

        # Handshake
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
                "turn_detection": None,
                "tools": TOOLS,
                "tool_choice": "auto",
            }
        }))

        raw = await ws.recv()
        if json.loads(raw).get("type") == "session.updated":
            print("✅ Session configured — ready\n")

        # Conversation loop
        interrupted = False

        while True:
            if not interrupted:
                user_input = await loop.run_in_executor(
                    None, get_input, "> Press Enter to speak (or type 'quit'): "
                )
                if user_input.strip().lower() == "quit":
                    break
                print("🟢 Listening...")

            # --- Recording ---
            if interrupted:
                # Clear any leftover audio from the cancelled response before recording
                await ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
                print("🎤 Go ahead — press Enter when done speaking")
            await do_recording(ws, loop)

            # Commit and request response
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            await ws.send(json.dumps({"type": "response.create"}))
            t_committed = time.perf_counter()

            # Start audio player thread — stoppable via stop_playback event
            play_queue: queue.Queue = queue.Queue()
            stop_playback = threading.Event()
            player = threading.Thread(
                target=audio_player, args=(play_queue, stop_playback), daemon=True
            )
            player.start()

            interrupt_event = asyncio.Event()

            async def watch_for_interrupt():
                await loop.run_in_executor(None, get_input)
                print("⚡ Enter pressed — interrupting...")
                interrupt_event.set()
                stop_playback.set()
                drain_queue(play_queue)

            print("🤖 Thinking...  (press Enter to interrupt)")
            interrupt_task = asyncio.create_task(watch_for_interrupt())
            response_task = asyncio.create_task(
                receive_response(ws, play_queue, t_committed, interrupt_event)
            )

            await response_task
            # Player may still be playing — wait for it (returns instantly if interrupted)
            await loop.run_in_executor(None, player.join)
            interrupt_task.cancel()

            user_text, assistant_text, _ = response_task.result()
            interrupted = interrupt_event.is_set()

            if not interrupted:
                t_end = time.perf_counter()
                print(f"⏱  Commit → playback end:   {t_end - t_committed:.2f}s")

            if assistant_text:
                print(f"✅ Assistant: {assistant_text}\n")

            # Only save complete (non-interrupted) turns to the transcript
            if not interrupted:
                if user_text:
                    conversation_log.append({"role": "user", "text": user_text})
                if assistant_text:
                    conversation_log.append({"role": "assistant", "text": assistant_text})

    # Transcript
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
