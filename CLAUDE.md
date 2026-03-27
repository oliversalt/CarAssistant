# CLAUDE.md

# CarPi — Raspberry Pi Car Assistant

A voice-activated AI assistant designed to run in a car, built on a Raspberry Pi 4B.
The user speaks, Whisper transcribes, Claude responds, ElevenLabs speaks the response aloud.

## Architecture

```
Microphone → PyAudio → Whisper STT → Claude API → ElevenLabs TTS → Speaker
```

State machine: IDLE → LISTENING → THINKING → SPEAKING → IDLE

## Hardware (target deployment)

- Raspberry Pi 4B 4GB running Raspberry Pi OS Lite
- AB13X USB mic/speaker combo
- 3.2" IPS HDMI display (800x480) for status display
- GPIO screw terminal HAT for buttons and RGB LED
- Powered by Belkin 20K USB-C power bank

## Tech Stack

- Python 3.11+
- PyAudio — mic recording and speaker playback
- OpenAI Whisper API (`whisper-1`) — speech to text
- Anthropic Claude API (`claude-sonnet-4-5`) — AI brain
- ElevenLabs API (`eleven_flash_v2_5`) — text to speech
- pydub + ffmpeg — MP3 decoding
- pygame — display UI (Phase 7)
- RPi.GPIO — buttons and LED (Phase 6)
- python-dotenv — API key management

## Key Config

- MIC_INDEX = 1 (AB13X USB mic, PC dev) — will differ on Pi
- SPEAKER_INDEX = 8 (AB13X USB speaker, PC dev) — will differ on Pi
- ElevenLabs voice: `JBFqnCBsd6RMkjVDRZzb` (George)
- Recording duration: 5 seconds (silence detection to be added later)

## Project Structure

```
carpi/
├── CLAUDE.md
├── .env                  # API keys — never commit
├── requirements.txt
├── venv/
├── test_mic.py           # PyAudio mic/speaker test
├── test_whisper.py       # Whisper STT test
├── test_claude.py        # Claude API test
├── test_tts.py           # ElevenLabs TTS test
├── test_pipeline.py      # Full end-to-end pipeline test
└── main.py               # Final conversation loop (in progress)
```

## Environment Variables

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
ELEVENLABS_API_KEY=
```

## Commands

```bash
# activate venv (Windows)
venv\Scripts\activate

# install dependencies
pip install -r requirements.txt

# run pipeline test
python test_pipeline.py

# run main app
python main.py
```

## Development Approach

- Develop and test everything on PC first
- Deploy to Pi only once PC version is stable (Phase 5)
- SSH into Pi via Tailscale (hostname: salt-raspberry-pi)
- Deploy via GitHub — never SCP code, only SCP the .env file
- Pi will autostart main.py via systemd on boot

## Current Phase

Phase 3 — building conversation loop in main.py
PC audio pipeline is fully working end to end.

## Code Style

- No markdown in Claude system prompt responses — spoken language only
- Keep Claude responses concise (max_tokens: 256)
- All timing instrumentation uses time.perf_counter()
- Print statements use emoji prefixes for readability (🎤 💬 🤖 🔊 ✅ ⚠️)
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

