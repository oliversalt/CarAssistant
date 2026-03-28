**Phase 1 — Environment setup (PC)**

Get your development environment ready on your PC before touching the Pi for code.

- Install Python 3.11+ on your PC
- Install VS Code with the Python extension and Copilot
- Create a project folder `carpi/`
- Set up a virtual environment inside it: `python -m venv venv`
- Create a `.env` file for API keys — never hardcode them
- Sign up for Claude API, OpenAI (for Whisper STT), and ElevenLabs — get API keys for all three
- Install initial dependencies: `pip install anthropic openai elevenlabs python-dotenv pyaudio`
- Commit everything to a private GitHub repo immediately — this is how you'll deploy to the Pi later

---

**Phase 2 — Voice pipeline on PC**

Get audio in and audio out working on your PC first. This is the core of the whole project.

- Test microphone recording with `pyaudio` — record a 5 second clip and save it as a wav file
- Send that wav file to OpenAI Whisper API and get back transcribed text — print it to the terminal
- Send that text to Claude API with a basic system prompt and get a response back
- Send that response text to ElevenLabs and get back an audio file
- Play that audio file through your PC speakers

When those four steps work end to end on your PC, the hardest part of the project is done. The rest is wrapping it in better code and adding hardware.

---

**Phase 3 — Conversation loop on PC**

Turn the one-shot pipeline into a proper conversation.

- Wrap everything in a loop that maintains conversation history
- Write the system prompt — tell Claude it's a car assistant, keep responses concise, no markdown, natural spoken language
- Add keyboard input to simulate the button press — press Enter to start recording, press Enter again to stop
- Add a simple state machine: IDLE → LISTENING → THINKING → SPEAKING → IDLE
- Add interrupt handling — pressing Enter during SPEAKING stops playback and returns to IDLE
- Test a full back and forth conversation entirely from your PC terminal

---

**Phase 4 — Robustness on PC**

Make it reliable before adding hardware complexity.

- Add proper error handling for every API call — what happens if Whisper fails, if Claude times out, if ElevenLabs is slow
- Add retry logic for transient API failures
- Add a timeout on recording — if no audio detected for 30 seconds auto-cancel
- Add conversation reset logic — clear history after a configurable number of turns or time period
- Write a simple config file for things you'll want to tweak — max conversation length, ElevenLabs voice ID, Claude model, system prompt
- Test edge cases — what if you press the button and say nothing, what if the API is down, what if the response is very long

---

**Phase 5 — Deploy to Pi and test audio hardware**

Push your working code to the Pi and verify the physical audio works.

- Push to GitHub from your PC
- SSH into Pi, clone the repo: `git clone https://github.com/yourname/carpi`
- Install dependencies on the Pi: `pip install -r requirements.txt`
- Copy your `.env` file to the Pi manually over SCP — never commit API keys to GitHub
- Test the microphone is recognised: `arecord -l` should list it
- Test the speaker is recognised: `aplay -l` should list it
- Configure the Pi to use your USB mic and USB speaker as default audio devices
- Run the script and test the full pipeline on the Pi with real hardware audio
- Adjust microphone input levels if needed using `alsamixer`

---

**Phase 6 — GPIO buttons and LED on Pi**

Wire up and code the physical controls.

- Wire your two button modules and LED to the GPIO screw terminal HAT as per the wiring diagram
- Install RPi.GPIO: `pip install RPi.GPIO`
- Write a simple test script that prints to terminal when each button is pressed and toggles the LED — verify wiring is correct before integrating
- Replace the keyboard Enter simulation from Phase 3 with the actual GPIO button
- Wire the LED to reflect state — slow pulse when idle, solid when listening, off when thinking, on when speaking
- Add the shutdown button functionality — hold button 2 for 3 seconds triggers `sudo shutdown now`
- Test the full flow with physical buttons

---

**Phase 7 — Screen UI on Pi**

Add the pygame display.

- Install pygame: `pip install pygame`
- Configure pygame to run on the Pi's display without a desktop — set the SDL environment variable: `export SDL_VIDEODRIVER=fbcon`
- Build each screen state as a simple pygame scene: IDLE (clock + ready indicator), LISTENING (waveform animation), THINKING (spinner + transcription text), SPEAKING (response text)
- Connect each state to your state machine from Phase 3
- Test all states transition correctly during a real conversation
- Tune font sizes and layout for readability at a glance

---

**Phase 8 — Autostart on boot**

Make it start automatically when the Pi powers on.

- Write a systemd service file that launches your Python script on boot
- Configure it to restart automatically if it crashes
- Test by rebooting the Pi with no SSH connection — it should be ready to use within 90 seconds of power on
- Test the shutdown button turns it off cleanly

---

**Phase 9 — Car testing**

Take it to the car and find the real world problems.

- Test microphone pickup with road noise — you'll likely need to adjust recording levels
- Test the push-to-talk flow while actually driving — is the button in a good position
- Test hotspot connection reliability — does it reconnect cleanly if the hotspot drops
- Test in direct sunlight — can you read the screen
- Test cold boot in a cold car — does it connect and start correctly
- Note everything that feels awkward and iterate

---

**Phase 10 — Case and final install**

Once the software is solid, build the permanent housing.

- Design the case in Fusion 360 or FreeCAD around your confirmed component layout
- Print in PETG
- Mount everything permanently with proper cable management
- Final test of the complete assembled unit