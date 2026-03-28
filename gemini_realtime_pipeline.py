"""
Gemini Live Pipeline — gemini-3.1-flash-live-preview
------------------------------------------------------
Uses the Google Gemini Live API (BidiGenerateContent) over a persistent WebSocket.
Push-to-talk: press Enter to start speaking, press Enter again to stop.
Press Enter while the model is speaking to interrupt it and start talking.
Press # to dismiss the model and return to idle without recording.
The WebSocket stays open between turns — no reconnection delay.
Prints a full conversation transcript when you quit.

Requires GEMINI_API_KEY in .env.

Usage:
    python gemini_realtime_pipeline.py
"""

import asyncio
import base64
import json
import msvcrt
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
MIC_RATE = 16000    # Gemini Live expects 16 kHz PCM16 input
OUT_RATE = 24000    # Gemini Live outputs 24 kHz PCM16
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024

MODEL = "gemini-3.1-flash-live-preview"
VOICE = "Algieba"   # options: Puck, Charon, Kore, Fenrir, Aoede, Algieba


def _upcase_types(schema: dict) -> dict:
    """Recursively convert JSON Schema type values to uppercase (Gemini requirement)."""
    result = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            result[k] = v.upper()
        elif isinstance(v, dict):
            result[k] = _upcase_types(v)
        elif isinstance(v, list):
            result[k] = [_upcase_types(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result


# Convert OpenAI Realtime tool schema → Gemini functionDeclarations format
TOOLS_GEMINI = [
    {
        "functionDeclarations": [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": _upcase_types(t["parameters"]),
            }
            for t in TOOLS
        ]
    }
]

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


def _ws_url(api_key: str) -> str:
    return (
        "wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
        f"?key={api_key}"
    )


# ---------------------------------------------------------------------------
# EnterQueue — one stdin thread, queues every key press
# ---------------------------------------------------------------------------

class EnterQueue:
    """
    Single background thread reads keyboard input forever via msvcrt.
    Every Enter press queues "". # queues "#". Ctrl+C queues "quit".

    Also maintains an asyncio.Event (_press_event) that is set whenever any
    key lands in the queue. receive_response() races ws.recv() against this
    event so interrupts are detected in <1ms instead of after the next WS
    message arrives.
    """

    def __init__(self):
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._press_event: asyncio.Event | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop):
        """Call once from the asyncio thread before start()."""
        self._loop = loop
        self._press_event = asyncio.Event()

    def start(self):
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def _reader(self):
        while True:
            ch = msvcrt.getwch()
            if ch in ('\r', '\n'):
                print("⌨️  Enter pressed")
                self._q.put("")
            elif ch == '#':
                print("⌨️  # pressed")
                self._q.put("#")
            elif ch == '\x03':  # Ctrl+C
                self._q.put("quit")
            else:
                continue
            # Wake up any asyncio task waiting on _press_event
            if self._loop and self._press_event:
                self._loop.call_soon_threadsafe(self._press_event.set)

    def poll(self) -> "str | None":
        """Non-blocking: returns '' for Enter, '#' for hash, 'quit' for Ctrl+C, or None."""
        try:
            return self._q.get_nowait()
        except queue.Empty:
            return None

    def drain(self):
        """Discard all queued key presses and clear the press event."""
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        if self._press_event:
            self._press_event.clear()

    async def wait(self) -> str:
        """Async: waits until the next key press, returns the queued value."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._q.get)

    async def wait_press(self):
        """Async: waits until _press_event is set (a key was pressed)."""
        if self._press_event:
            await self._press_event.wait()


# ---------------------------------------------------------------------------
# Audio playback — runs in its own thread
# ---------------------------------------------------------------------------

def audio_player(play_queue: queue.Queue, stop_event: threading.Event):
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=OUT_RATE, output=True)
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
# Mic streaming — async task, sends 16kHz PCM16 audio chunks
# ---------------------------------------------------------------------------

async def stream_mic(ws, stop_event: asyncio.Event):
    loop = asyncio.get_event_loop()
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=MIC_RATE,
                    input=True, input_device_index=MIC_INDEX,
                    frames_per_buffer=CHUNK)
    try:
        while not stop_event.is_set():
            data = await loop.run_in_executor(None, stream.read, CHUNK)
            b64 = base64.b64encode(data).decode()
            await ws.send(json.dumps({
                "realtimeInput": {
                    "audio": {
                        "data": b64,
                        "mimeType": f"audio/pcm;rate={MIC_RATE}",
                    }
                }
            }))
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


# ---------------------------------------------------------------------------
# Incoming drain — runs alongside stream_mic to keep the WebSocket alive
# ---------------------------------------------------------------------------

async def drain_incoming(ws, stop_event: asyncio.Event):
    """
    Reads and discards all incoming server messages during the recording phase.
    Without this, server WebSocket keepalive pings go unanswered and the server
    closes the connection with 1011 keepalive ping timeout.
    Also discards any stale model-generation messages from a previous interrupted turn.
    """
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.1)
        except asyncio.TimeoutError:
            continue
        except Exception:
            break


# ---------------------------------------------------------------------------
# Response receiver — races ws.recv() against EnterQueue press event
# ---------------------------------------------------------------------------

async def receive_response(
    ws,
    play_queue: queue.Queue,
    stop_playback: threading.Event,
    enters: EnterQueue,
    t_committed: float,
) -> tuple[str, bool, bool]:
    """
    Reads WebSocket events until turnComplete (or interrupt/dismiss).

    After every ws.recv() we also race against enters._press_event so that a
    key press wakes us up immediately — no waiting for the next WS message.

    Returns (assistant_transcript, was_interrupted, was_dismissed).
    was_interrupted=True → Enter pressed mid-response, start recording immediately.
    was_dismissed=True   → # pressed, stop speaking, return to idle.
    """
    assistant_text = ""
    t_first_audio = None

    # Discard stale Enter presses (e.g. the stop-recording press)
    enters.drain()

    loop = asyncio.get_event_loop()

    while True:
        # Race: next WS message vs. a key press
        recv_fut = loop.create_task(ws.recv())
        press_fut = loop.create_task(enters.wait_press())

        done, pending = await asyncio.wait(
            {recv_fut, press_fut},
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel whatever didn't finish
        for fut in pending:
            fut.cancel()
            try:
                await fut
            except (asyncio.CancelledError, Exception):
                pass

        # --- Key press won the race ---
        if press_fut in done and press_fut not in pending:
            key = enters.poll()
            enters.drain()  # discard any further presses
            if key == "" or key == "#":
                is_dismiss = (key == "#")
                label = "# pressed — dismissing..." if is_dismiss else "Enter pressed — interrupting..."
                print(f"⚡ {label}")
                stop_playback.set()
                drain_queue(play_queue)
                # recv_fut was already cancelled; ws state is intact
                return assistant_text, not is_dismiss, is_dismiss
            # "quit" or unexpected — fall through to check recv
            if recv_fut not in done:
                continue

        # --- WS message arrived ---
        if recv_fut not in done:
            # Only press_fut done but no actionable key (shouldn't happen often)
            enters._press_event.clear()
            continue

        try:
            raw = recv_fut.result()
        except Exception as e:
            print(f"⚠️  WS recv error: {e}")
            break

        # Clear the press event only if there's nothing queued
        if enters._q.empty() and enters._press_event:
            enters._press_event.clear()

        event = json.loads(raw)

        sc = event.get("serverContent", {})
        if sc:
            model_turn = sc.get("modelTurn", {})
            for part in model_turn.get("parts", []):
                if "inlineData" in part:
                    audio_data = base64.b64decode(part["inlineData"]["data"])
                    if t_first_audio is None:
                        t_first_audio = time.perf_counter()
                        print(f"⏱  Commit → first audio:    {t_first_audio - t_committed:.2f}s")
                    play_queue.put(audio_data)
                elif "text" in part:
                    assistant_text += part["text"]

            if sc.get("turnComplete"):
                t_done = time.perf_counter()
                print(f"⏱  Commit → response done:  {t_done - t_committed:.2f}s")
                break

            if sc.get("interrupted"):
                break

        tool_call = event.get("toolCall")
        if tool_call:
            responses = []
            for fn_call in tool_call.get("functionCalls", []):
                args = fn_call.get("args", {})
                result = dispatch(fn_call["name"], args)
                responses.append({
                    "id": fn_call["id"],
                    "name": fn_call["name"],
                    "response": {"result": result},
                })
            await ws.send(json.dumps({
                "toolResponse": {"functionResponses": responses}
            }))

        if "error" in event:
            print(f"⚠️  API error: {event['error']}")
            break

    play_queue.put(None)
    return assistant_text, False, False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("⚠️  GEMINI_API_KEY not set in .env")
        return

    print("=" * 50)
    print("🚗 CarPi — Gemini Live Pipeline")
    print(f"   Model: {MODEL}  |  Voice: {VOICE}")
    print("   Press Enter to start speaking.")
    print("   Press Enter again to stop and get a response.")
    print("   Press Enter while the model is speaking to interrupt it.")
    print("   Press # to dismiss the model without recording.")
    print("   Press Ctrl+C to exit.")
    print("=" * 50)

    loop = asyncio.get_event_loop()
    enters = EnterQueue()
    enters.attach_loop(loop)
    enters.start()

    conversation_log = []

    async with websockets.connect(_ws_url(api_key)) as ws:

        # Handshake — send setup, wait for setupComplete
        await ws.send(json.dumps({
            "setup": {
                "model": f"models/{MODEL}",
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": VOICE}
                        }
                    },
                },
                "systemInstruction": {
                    "parts": [{"text": SYSTEM_PROMPT}]
                },
                "tools": TOOLS_GEMINI,
                # Disable automatic VAD so we control turn boundaries manually.
                # activityStart interrupts the model; activityEnd triggers generation.
                "realtimeInputConfig": {
                    "automaticActivityDetection": {"disabled": True},
                    "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
                },
            }
        }))

        raw = await ws.recv()
        event = json.loads(raw)
        if "setupComplete" not in event:
            print(f"⚠️  Unexpected first event: {event}")
            return
        print("✅ Session created — ready\n")

        interrupted = False
        dismissed = False

        while True:

            # --- Wait for Enter to start a turn ---
            if not interrupted:
                print("> Press Enter to speak (Ctrl+C to quit)", flush=True)
                text = await enters.wait()
                if text == "quit":
                    break
                print("🟢 Listening...")
            else:
                enters.drain()  # clear stale presses from the interrupt period
                print("⚡ Interrupted — speak now, press Enter when done")

            # Signal start of user speech.
            # activityStart interrupts any ongoing model generation server-side.
            await ws.send(json.dumps({"realtimeInput": {"activityStart": {}}}))

            # --- Record (stream_mic + drain_incoming run concurrently) ---
            print("🎤 Recording... press Enter to stop")
            t_record_start = time.perf_counter()
            stop_recording = asyncio.Event()
            mic_task = asyncio.create_task(stream_mic(ws, stop_recording))
            drain_task = asyncio.create_task(drain_incoming(ws, stop_recording))

            await enters.wait()
            print("⏹  Recording stopped")
            stop_recording.set()
            await mic_task
            drain_task.cancel()
            try:
                await drain_task
            except asyncio.CancelledError:
                pass
            print(f"⏱  Recording duration:      {time.perf_counter() - t_record_start:.2f}s")

            # Signal end of user speech — triggers model generation
            await ws.send(json.dumps({"realtimeInput": {"activityEnd": {}}}))
            t_committed = time.perf_counter()

            # --- Start audio player ---
            play_queue: queue.Queue = queue.Queue()
            stop_playback = threading.Event()
            player = threading.Thread(
                target=audio_player, args=(play_queue, stop_playback), daemon=True
            )
            player.start()

            # --- Receive response (interrupt detection is inside via event racing) ---
            print("🤖 Thinking...  (press Enter to interrupt, # to dismiss)")
            assistant_text, interrupted, dismissed = await receive_response(
                ws, play_queue, stop_playback, enters, t_committed,
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
                        dismissed = True
                        break
                    await asyncio.sleep(0.05)

            player.join()

            if not interrupted and not dismissed:
                print(f"⏱  Commit → playback end:   {time.perf_counter() - t_committed:.2f}s")

            if assistant_text:
                print(f"\n✅ Assistant: {assistant_text}\n")
                suffix = " [interrupted]" if interrupted else (" [dismissed]" if dismissed else "")
                conversation_log.append({"role": "assistant", "text": assistant_text + suffix})

            # # key returns to idle without entering recording mode
            if dismissed:
                interrupted = False

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
