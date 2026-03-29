"""
CarPi UI v2
Animated character display with clock and state badge.

On PC (auto-detected): python screen-ui/carpi_ui_v2.py
On Pi:                 python screen-ui/carpi_ui_v2.py  (writes to /dev/fb0)
"""

import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Layout config
# ---------------------------------------------------------------------------

SCREEN_W = 800
SCREEN_H = 480
CHAR_H   = 440   # animation frames scaled to this height

BG        = (255, 255, 255)
TEXT_DARK = (20, 20, 20)
TEXT_MID  = (140, 140, 140)

BADGE_COLOURS = {
    "READY":     ((230, 255, 235), (30, 160, 60)),
    "LISTENING": ((255, 248, 225), (200, 140, 0)),
    "THINKING":  ((235, 235, 255), (70, 70, 220)),
    "SPEAKING":  ((225, 248, 255), (0, 150, 190)),
    "NO WIFI":   ((255, 238, 230), (210, 80, 30)),
    "ERROR":     ((255, 230, 230), (200, 30, 30)),
}

_BADGE_MAP = {
    "DISMISSED": "READY",   # # pressed — badge shows READY while anim plays
}

# ---------------------------------------------------------------------------
# Animation sequence definitions
# ---------------------------------------------------------------------------

SEQ_BASE = Path(__file__).parent.parent / "sequences"

_SEQ_DEFS: dict[str, dict] = {
    # ── Startup ──────────────────────────────────────────────────────────────
    "waking_up": {
        "folder": "waking_up",
        "files":  ["0.png","1.png","3.png","4.png","5.png","6.png",
                   "7.png","8.png","9.png","10.png","11.png"],
        "ms": 200, "loop": False,
    },
    # ── Idle ─────────────────────────────────────────────────────────────────
    "idle": {
        "folder": "idle_1",
        "files":  ["1.png","2.png","3.png","4.png","5.png","6.png"],
        "ms": 450, "loop": True,
    },
    # ── Idle fidget animations (play occasionally, then return to idle) ───────
    "idle_fidget_1": {
        "folder": "default_to_idle_animation_1",
        "files":  ["2.png","3.png","4.png","5.png","6.png","7.png","8.png","9.png"],
        "ms": 500, "loop": False,
    },
    "idle_fidget_2": {
        "folder": "default_to_idle_animation_2",
        "files":  ["(1).png","(2).png","(3).png","(4).png","(5).png","(6).png","(7).png",
                   "(8).png","(9).png","(10).png","(11).png","(12).png","(13).png","(14).png"],
        "ms": 350, "loop": False,
    },
    # ── Listening variant 1: loops whole animation while listening ────────────
    "listen_1_loop": {
        "folder": "default_to_listen_1",
        "files":  [
            "deault_to_listen (1).png",
            "deault_to_listen (2).png",
            "deault_to_listen (3).png",
            "deault_to_listen (4).png",
            "deault_to_listen (5).png",
            "deault_to_listen (6).png",
            "deault_to_listen (7).png",
            "deault_to_listen (8) - Copy.png",
            "deault_to_listen (9) - Copy.png",
            "deault_to_listen (10) - Copy.png",
            "deault_to_listen (11) - Copy.png",
            "deault_to_listen (12) - Copy.png",
        ],
        "ms": 300, "loop": True,
    },
    # ── Listening variant 2: intro then hold on frame 5 ──────────────────────
    "listen_2_intro": {
        "folder": "default_to_listen_2",
        "files":  ["1.png","2.png","3.png","4.png"],
        "ms": 200, "loop": False,          # was 350ms — sped up
    },
    "listen_2_hold": {
        "folder": "default_to_listen_2",
        "files":  ["5.png"],
        "ms": 60_000, "loop": True,        # holds until state changes
    },
    # ── Thinking ─────────────────────────────────────────────────────────────
    "thinking": {
        "folder": "thinking_loop",
        "files":  ["2.png","3.png","4.png","5.png","6.png","7.png","8.png","9.png"],
        "ms": 100, "loop": True,
    },
    # ── Speaking ─────────────────────────────────────────────────────────────
    "speaking": {
        "folder": "speaking",
        "files":  [f"speaking ({i}).png" for i in range(1, 20)],
        "ms": 130, "loop": True,
    },
    # ── Dismissed (#) ─────────────────────────────────────────────────────────
    "interrupted": {
        "folder": "interupted_to_default",
        "files":  ["1.png"],
        "ms": 700, "loop": False,
    },
    # ── Error ────────────────────────────────────────────────────────────────
    "error_intro": {
        "folder": "error",
        "files":  ["0.png","1.png","2.png","3.png","4.png",
                   "5.png","6.png","7.png","8.png","9.png"],
        "ms_list": [16, 100, 100, 200, 200, 200, 200, 200, 200, 200],
        "loop": False,
    },
    "error_loop": {
        "folder": "error",
        "files":  ["10.png","11.png","12.png","13.png","14.png"],
        "ms_list": [100, 100, 750, 750, 750],
        "loop": True,
    },
    # ── No connection ────────────────────────────────────────────────────────
    "no_wifi": {
        "folder": "no connection",
        "files":  ["1.png"],
        "ms": 60_000, "loop": True,
    },
}

# ---------------------------------------------------------------------------
# Frame loading — all frames pre-loaded at startup
# ---------------------------------------------------------------------------

def _scale(img: Image.Image, height: int) -> Image.Image:
    return img.resize((int(img.width * height / img.height), height), Image.LANCZOS)


def _load_seq(name: str) -> tuple[list[Image.Image], list[int], bool]:
    d      = _SEQ_DEFS[name]
    folder = SEQ_BASE / d["folder"]
    frames = [_scale(Image.open(folder / f).convert("RGBA"), CHAR_H) for f in d["files"]]
    durations = d.get("ms_list") or [d["ms"]] * len(frames)
    return frames, durations, d["loop"]


print("⏳ Loading animation frames...", flush=True)
_SEQS: dict[str, tuple[list[Image.Image], list[int], bool]] = {
    name: _load_seq(name) for name in _SEQ_DEFS
}
print(f"✅ {sum(len(v[0]) for v in _SEQS.values())} frames across {len(_SEQS)} sequences.", flush=True)

# ---------------------------------------------------------------------------
# Animation player
# ---------------------------------------------------------------------------

class _Player:
    def __init__(self) -> None:
        self._frames: list[Image.Image] = []
        self._durations: list[int]      = []
        self._loop: bool                = True
        self._idx: int                  = 0
        self._next_at: float            = 0.0
        self._done: bool                = False

    def load(self, name: str) -> None:
        frames, durations, loop = _SEQS[name]
        self._frames    = frames
        self._durations = durations
        self._loop      = loop
        self._idx       = 0
        self._done      = False
        self._started   = False   # timer starts on first tick, not on load
        self._next_at   = 0.0

    def tick(self) -> bool:
        """Advance if due. Returns True when a non-looping animation finishes."""
        if self._done or not self._frames:
            return self._done
        if not self._started:
            # Start the clock from the first rendered frame, not from load time.
            # This prevents fast-forwarding through frames when loading is slow.
            self._started = True
            self._next_at = time.perf_counter() + self._durations[0] / 1000.0
            return False
        if time.perf_counter() < self._next_at:
            return False
        self._idx += 1
        if self._idx >= len(self._frames):
            if self._loop:
                self._idx = 0
            else:
                self._idx = len(self._frames) - 1
                self._done = True
                return True
        self._next_at = time.perf_counter() + self._durations[self._idx] / 1000.0
        return False

    @property
    def current(self) -> Image.Image:
        if not self._frames:
            return Image.new("RGBA", (CHAR_H, CHAR_H), (0, 0, 0, 0))
        return self._frames[self._idx]


# ---------------------------------------------------------------------------
# Animation state machine
# ---------------------------------------------------------------------------

_player = _Player()
_anim_state: str          = "waking_up"
_prev_pipeline_state: str = ""
_listen_variant: int      = 1         # 1 or 2, randomised each LISTENING trigger
_fidget_due_at: float     = 0.0       # perf_counter timestamp for next idle fidget

_player.load("waking_up")

# These animations finish on their own schedule — READY won't interrupt them
_PROTECTED = {"interrupted", "idle_fidget_1", "idle_fidget_2"}


def _next_fidget_time() -> float:
    return time.perf_counter() + random.uniform(10.0, 15.0)


def _switch(name: str) -> None:
    global _anim_state
    _anim_state = name
    _player.load(name)


def _tick_anim(pipeline_state: str) -> None:
    global _prev_pipeline_state, _listen_variant, _fidget_due_at

    # ── Waking up plays fully through before any pipeline state is processed ──
    if _anim_state == "waking_up":
        _prev_pipeline_state = pipeline_state  # stay in sync but don't act
        done = _player.tick()
        if done:
            _switch("idle")
            _fidget_due_at = _next_fidget_time()
        return

    # ── Handle pipeline state changes ────────────────────────────────────────
    if pipeline_state != _prev_pipeline_state:
        _prev_pipeline_state = pipeline_state

        if pipeline_state == "DISMISSED":
            _switch("interrupted")

        elif pipeline_state == "LISTENING":
            _listen_variant = random.choice([1, 2])
            if _listen_variant == 1:
                _switch("listen_1_loop")
            else:
                _switch("listen_2_intro")

        elif pipeline_state == "THINKING":
            _switch("thinking")

        elif pipeline_state == "SPEAKING":
            _switch("speaking")

        elif pipeline_state == "READY":
            if _anim_state not in _PROTECTED:
                _switch("idle")
                _fidget_due_at = _next_fidget_time()

        elif pipeline_state == "ERROR":
            _switch("error_intro")

        elif pipeline_state == "NO WIFI":
            _switch("no_wifi")

    # ── Idle fidget trigger ───────────────────────────────────────────────────
    if (pipeline_state == "READY"
            and _anim_state == "idle"
            and time.perf_counter() >= _fidget_due_at):
        _switch(random.choice(["idle_fidget_1", "idle_fidget_2"]))

    # ── Advance frame ─────────────────────────────────────────────────────────
    done = _player.tick()

    # ── Auto-transitions on non-looping animation completion ─────────────────
    if done:
        if _anim_state == "waking_up":
            _switch("idle")
            _fidget_due_at = _next_fidget_time()

        elif _anim_state == "listen_2_intro":
            _switch("listen_2_hold")

        elif _anim_state in ("idle_fidget_1", "idle_fidget_2"):
            _switch("idle")
            _fidget_due_at = _next_fidget_time()

        elif _anim_state == "interrupted":
            _switch("idle")
            _fidget_due_at = _next_fidget_time()

        elif _anim_state == "error_intro":
            _switch("error_loop")


# ---------------------------------------------------------------------------
# Display backend
# ---------------------------------------------------------------------------

_PREVIEW = (
    os.environ.get("CARPI_PREVIEW", "").lower() == "true"
    or sys.platform == "win32"
    or not Path("/dev/fb0").exists()
)

if _PREVIEW:
    import tkinter as tk
    from PIL import ImageTk

    _root = tk.Tk()
    _root.title("CarPi UI v2")
    _root.geometry(f"{SCREEN_W}x{SCREEN_H}")
    _root.resizable(False, False)
    _label = tk.Label(_root, bd=0)
    _label.pack()
    _photo_ref = None

    def show_frame(img: Image.Image) -> None:
        global _photo_ref
        _photo_ref = ImageTk.PhotoImage(img.convert("RGB"))
        _label.config(image=_photo_ref)
        _root.update()

else:
    _fb = open("/dev/fb0", "wb")

    def show_frame(img: Image.Image) -> None:
        r, g, b, a = img.split()
        bgra = Image.merge("RGBA", (b, g, r, a))
        _fb.seek(0)
        _fb.write(bgra.tobytes())
        _fb.flush()

# ---------------------------------------------------------------------------
# Frame rendering
# ---------------------------------------------------------------------------

def _load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


FONTS = {
    "clock": _load_font(["C:/Windows/Fonts/bahnschrift.ttf",
                          "C:/Windows/Fonts/segoeuib.ttf",
                          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"], 86),
    "date":  _load_font(["C:/Windows/Fonts/bahnschrift.ttf",
                          "C:/Windows/Fonts/segoeui.ttf",
                          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],      18),
    "badge": _load_font(["C:/Windows/Fonts/bahnschrift.ttf",
                          "C:/Windows/Fonts/segoeuib.ttf",
                          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"], 40),
}

_BASE = Image.new("RGBA", (SCREEN_W, SCREEN_H), BG + (255,))


def _draw_badge(draw: ImageDraw.Draw, label: str) -> None:
    fill, text_col = BADGE_COLOURS[label]
    pad_x, pad_y = 35, 20
    bbox = draw.textbbox((0, 0), label, font=FONTS["badge"])
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    bw, bh = tw + pad_x * 2, th + pad_y * 2
    bx = SCREEN_W - 32 - bw
    by = 36
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=fill)
    draw.text((bx + pad_x, by + pad_y), label, font=FONTS["badge"], fill=text_col)


def draw_frame(pipeline_state: str) -> Image.Image:
    """
    Advance animation state machine and return a composited frame.
    Call once per display tick, passing the current pipeline state string.
    """
    _tick_anim(pipeline_state)

    img  = _BASE.copy()
    char = _player.current
    img.paste(char, ((SCREEN_W - char.width) // 2, (SCREEN_H - char.height) // 2), char)

    draw = ImageDraw.Draw(img)
    now  = datetime.now()
    draw.text((32, 24),  now.strftime("%H:%M"),            font=FONTS["clock"], fill=TEXT_DARK)
    draw.text((36, 118), now.strftime("%a %d %b").upper(), font=FONTS["date"],  fill=TEXT_MID)

    badge_label = _BADGE_MAP.get(pipeline_state, pipeline_state)
    if badge_label in BADGE_COLOURS:
        _draw_badge(draw, badge_label)

    return img


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

_DEMO_STATES = [
    ("READY",     12),   # 12 s idle — enough to see a fidget
    ("LISTENING",  4),
    ("THINKING",   3),
    ("SPEAKING",   5),
    ("DISMISSED",  2),
    ("ERROR",      5),
    ("NO WIFI",    4),
]

_running = True


def main() -> None:
    global _running

    fps        = 30
    frame_time = 1.0 / fps

    if _PREVIEW:
        print("CarPi UI v2  |  PC preview — close window or Ctrl+C to quit")
        _root.protocol("WM_DELETE_WINDOW", lambda: globals().update(_running=False))
    else:
        print("CarPi UI v2  |  Pi framebuffer — Ctrl+C to quit")

    import signal
    signal.signal(signal.SIGINT, lambda s, f: globals().update(_running=False))

    state_idx   = 0
    state_until = time.perf_counter() + _DEMO_STATES[0][1]

    while _running:
        t0 = time.perf_counter()

        # Advance demo state on timer
        if t0 >= state_until:
            state_idx   = (state_idx + 1) % len(_DEMO_STATES)
            state_until = t0 + _DEMO_STATES[state_idx][1]

        state = _DEMO_STATES[state_idx][0]
        show_frame(draw_frame(state))

        sleep = frame_time - (time.perf_counter() - t0)
        if sleep > 0:
            time.sleep(sleep)

    if not _PREVIEW:
        _fb.seek(0)
        _fb.write(bytes(SCREEN_W * SCREEN_H * 4))
        _fb.close()

    print("Done.")


if __name__ == "__main__":
    main()
