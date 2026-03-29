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
with ui:
    python openai_realtime_pipeline.py --screen
"""

import argparse
import asyncio
import base64
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
    def _read_key() -> str:
        return msvcrt.getwch()
else:
    import tty
    import termios
    def _read_key() -> str:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

import pyaudio
import websockets
from dotenv import load_dotenv

from tools import TOOLS, dispatch

load_dotenv()

# ---------------------------------------------------------------------------
# UI state — updated by the pipeline, read by the screen loop
# ---------------------------------------------------------------------------

_ui_state: str = "READY"

def set_state(s: str) -> None:
    global _ui_state
    _ui_state = s


if sys.platform == "win32":
    MIC_INDEX     = 1
    SPEAKER_INDEX = 8
else:  # Linux (Pi)
    MIC_INDEX     = 3
    SPEAKER_INDEX = 3
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
    "Spotify playlists appear that they don't have any songs in them but they do and you can play them with the tools provided. "
)


# ---------------------------------------------------------------------------
# EnterQueue — one stdin thread, queues every Enter press
# ---------------------------------------------------------------------------

class EnterQueue:
    """
    Single background thread reads stdin forever.
    Every Enter press is put into a thread-safe queue.
    Use wait() to block until the next press (async).
    Use poll() for a non-blocking check (sync, safe inside asyncio).
    """

    def __init__(self):
        self._q: queue.SimpleQueue = queue.SimpleQueue()

    def start(self):
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def _reader(self):
        while True:
            ch = _read_key()
            if ch in ('\r', '\n'):
                print("⌨️  Enter pressed")
                self._q.put("")
            elif ch == '#':
                print("⌨️  # pressed")
                self._q.put("#")
            elif ch == '\x03':  # Ctrl+C
                self._q.put("quit")
            # ignore all other keys

    def poll(self) -> "str | None":
        """Non-blocking: returns the key pressed ('' for Enter, '#' for hash) or None."""
        try:
            return self._q.get_nowait()
        except queue.Empty:
            return None

    def drain(self):
        """Discard all queued Enter presses."""
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    async def wait(self) -> str:
        """Async: waits until the next Enter press, returns whatever was typed."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._q.get)


# ---------------------------------------------------------------------------
# Audio playback — runs in its own thread
# ---------------------------------------------------------------------------

def audio_player(play_queue: queue.Queue, stop_event: threading.Event):
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True,
                    output_device_index=SPEAKER_INDEX)
    try:
        while not stop_event.is_set():
            chunk = play_queue.get()
            if chunk is None:
                break
            stream.write(chunk)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


def drain_queue(q: queue.Queue):
    while not q.empty():
        try:
            q.get_nowait()
        except queue.Empty:
            break
    q.put(None)


# ---------------------------------------------------------------------------
# Mic streaming — async task
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
# Response receiver — polls EnterQueue for interrupts after every WS event
# ---------------------------------------------------------------------------

async def receive_response(
    ws,
    play_queue: queue.Queue,
    stop_playback: threading.Event,
    enters: EnterQueue,
) -> tuple[str, str, bool, bool]:
    """
    Reads WebSocket events until response.done (or interrupt).
    Checks enters.poll() after every event — no separate task, no cancel races.
    Returns (user_transcript, assistant_transcript, was_interrupted, was_dismissed).
    was_interrupted=True  → Enter pressed mid-response, start recording immediately.
    was_dismissed=True    → # pressed, stop speaking, return to idle prompt.
    """
    user_text = ""
    assistant_text = ""
    pending_fn_calls: dict[str, dict] = {}
    _speaking_set = False

    # Discard any Enter presses that arrived before we started listening
    # (e.g. the stop-recording Enter, or a late press from the previous turn)
    enters.drain()

    async for raw in ws:

        # --- Check for keypress (poll is non-blocking) ---
        key = enters.poll()
        if key == "" or key == "#":
            is_dismiss = (key == "#")
            label = "# pressed — dismissing..." if is_dismiss else "Enter pressed — interrupting..."
            print(f"⚡ {label}")
            if is_dismiss:
                set_state("DISMISSED")
            await ws.send(json.dumps({"type": "response.cancel"}))
            stop_playback.set()
            drain_queue(play_queue)
            print("🧹 Draining cancelled response...")
            async for stale in ws:
                stale_type = json.loads(stale).get("type", "")
                if stale_type in ("response.cancelled", "response.done", "error"):
                    print("✅ Cancel confirmed")
                    break
            try:
                while True:
                    stale = await asyncio.wait_for(ws.recv(), timeout=0.3)
                    stale_type = json.loads(stale).get("type", "")
                    if stale_type in ("error", "session.created"):
                        break
            except asyncio.TimeoutError:
                pass
            return user_text, assistant_text, not is_dismiss, is_dismiss

        event = json.loads(raw)
        etype = event.get("type", "")

        if etype == "response.audio.delta":
            if not _speaking_set:
                set_state("SPEAKING")
                _speaking_set = True
            play_queue.put(base64.b64decode(event["delta"]))

        elif etype == "response.audio_transcript.delta":
            assistant_text += event.get("delta", "")

        elif etype == "conversation.item.input_audio_transcription.completed":
            user_text = event.get("transcript", "").strip()
            print(f"\n💬 You said: {user_text}\n")

        elif etype == "response.output_item.added":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                pending_fn_calls[item["call_id"]] = {"name": item["name"], "arguments": ""}

        elif etype == "response.function_call_arguments.delta":
            call_id = event.get("call_id")
            if call_id in pending_fn_calls:
                pending_fn_calls[call_id]["arguments"] += event.get("delta", "")

        elif etype == "response.done":
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
                _speaking_set = False
                set_state("THINKING")
                await ws.send(json.dumps({"type": "response.create"}))
            else:
                break

        elif etype == "error":
            print(f"⚠️  API error: {event.get('error', event)}")
            break

    play_queue.put(None)
    return user_text, assistant_text, False, False


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
    print("   Press # to dismiss the model without recording.")
    print("   Press Ctrl+C to exit.")
    print("=" * 50)

    enters = EnterQueue()
    enters.start()

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
            set_state("READY")

        interrupted = False

        while True:

            # --- Wait for Enter to start a turn ---
            if not interrupted:
                set_state("READY")
                print("> Press Enter to speak (Ctrl+C to quit)", flush=True)
                text = await enters.wait()
                if text == "quit":
                    break
                print("🟢 Listening...")
            else:
                await ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
                print("⚡ Interrupted — speak now, press Enter when done")

            # --- Record ---
            set_state("LISTENING")
            print("🎤 Recording... press Enter to stop")
            stop_recording = asyncio.Event()
            mic_task = asyncio.create_task(stream_mic(ws, stop_recording))

            await enters.wait()
            print("⏹  Recording stopped")
            stop_recording.set()
            await mic_task

            # --- Commit and request response ---
            set_state("THINKING")
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            await ws.send(json.dumps({"type": "response.create"}))

            # --- Start player ---
            play_queue: queue.Queue = queue.Queue()
            stop_playback = threading.Event()
            player = threading.Thread(
                target=audio_player, args=(play_queue, stop_playback), daemon=True
            )
            player.start()

            # --- Receive response (interrupt detection is inside via poll()) ---
            print("🤖 Thinking...  (press Enter to interrupt, # to dismiss)")
            user_text, assistant_text, interrupted, dismissed = await receive_response(
                ws, play_queue, stop_playback, enters
            )

            # --- Wait for playback, checking for interrupt/dismiss every 50ms ---
            if not interrupted and not dismissed:
                while player.is_alive():
                    key = enters.poll()
                    if key == "":
                        print("⚡ Enter pressed — stopping playback...")
                        stop_playback.set()
                        drain_queue(play_queue)
                        interrupted = True
                        break
                    elif key == "#":
                        print("⚡ # pressed — dismissing playback...")
                        stop_playback.set()
                        drain_queue(play_queue)
                        set_state("DISMISSED")
                        dismissed = True
                        break
                    await asyncio.sleep(0.05)

            player.join()

            if assistant_text:
                print(f"\n✅ Assistant: {assistant_text}\n")

            if user_text:
                conversation_log.append({"role": "user", "text": user_text})
            if assistant_text:
                suffix = " [interrupted]" if interrupted else (" [dismissed]" if dismissed else "")
                conversation_log.append({"role": "assistant", "text": assistant_text + suffix})

            # # key returns to idle without entering recording mode
            if dismissed:
                interrupted = False

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


def _run_pipeline():
    asyncio.run(main())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CarPi Realtime Pipeline")
    parser.add_argument("--screen", action="store_true",
                        help="Show the CarPi UI on screen alongside the terminal")
    args = parser.parse_args()

    if args.screen:
        # tkinter must live on the main thread — run asyncio pipeline in a thread
        sys.path.insert(0, str(Path(__file__).parent / "screen-ui"))
        import carpi_ui_v2 as ui

        pipeline_thread = threading.Thread(target=_run_pipeline, daemon=True)
        pipeline_thread.start()

        while pipeline_thread.is_alive():
            try:
                img = ui.draw_frame(_ui_state)
                ui.show_frame(img)
            except Exception:
                break
            time.sleep(1 / 30)
    else:
        _run_pipeline()
