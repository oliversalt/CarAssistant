"""
CarPi UI v2
White background, character image, clock, state badge.

On PC:  CARPI_PREVIEW=true python screen-ui/carpi_ui_v2.py
On Pi:  python screen-ui/carpi_ui_v2.py   (writes to /dev/fb0)
"""

import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCREEN_W = 800
SCREEN_H = 480
FPS = 30

BG       = (255, 255, 255)
TEXT_DARK = (20, 20, 20)
TEXT_MID  = (140, 140, 140)

# Badge: (background fill, text colour)
BADGE_COLOURS = {
    "READY":     ((230, 255, 235), (30, 160, 60)),
    "LISTENING": ((255, 248, 225), (200, 140, 0)),
    "THINKING":  ((235, 235, 255), (70, 70, 220)),
    "SPEAKING":  ((225, 248, 255), (0, 150, 190)),
    "NO WIFI":   ((255, 238, 230), (210, 80, 30)),
    "ERROR":     ((255, 230, 230), (200, 30, 30)),
}

STATES = ["READY", "LISTENING", "THINKING", "SPEAKING", "NO WIFI", "ERROR"]

CHARACTER_PATH   = Path(__file__).parent.parent / "animation" / "salty.png"
CHARACTER_HEIGHT = 480  # scale character to this height


# ---------------------------------------------------------------------------
# Display backend — only this section differs between PC and Pi
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
    _root.title("CarPi UI v2 Preview")
    _root.geometry(f"{SCREEN_W}x{SCREEN_H}")
    _root.resizable(False, False)
    _label = tk.Label(_root, bd=0)
    _label.pack()
    _photo_ref = None  # keep reference to prevent GC

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
# Assets & fonts — loaded once at startup
# ---------------------------------------------------------------------------

def _load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _get_fonts() -> dict:
    regular = [
        "C:/Windows/Fonts/bahnschrift.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    bold = [
        "C:/Windows/Fonts/bahnschrift.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    return {
        "clock": _load_font(bold,    86),
        "date":  _load_font(regular, 18),
        "badge": _load_font(bold,    40),
    }


def _load_character(height: int) -> Image.Image:
    img = Image.open(CHARACTER_PATH).convert("RGBA")
    aspect = img.width / img.height
    return img.resize((int(height * aspect), height), Image.LANCZOS)


FONTS     = _get_fonts()
CHARACTER = _load_character(CHARACTER_HEIGHT)

# Pre-built white base (never mutated — copy each frame)
_BASE = Image.new("RGBA", (SCREEN_W, SCREEN_H), BG + (255,))


# ---------------------------------------------------------------------------
# Frame rendering — identical on PC and Pi
# ---------------------------------------------------------------------------

def _draw_badge(draw: ImageDraw.Draw, state: str) -> None:
    fill, text_col = BADGE_COLOURS[state]
    pad_x, pad_y = 35, 20
    bbox = draw.textbbox((0, 0), state, font=FONTS["badge"])
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    bw = tw + pad_x * 2
    bh = th + pad_y * 2
    bx = SCREEN_W - 32 - bw
    by = 36
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=fill)
    draw.text((bx + pad_x, by + pad_y), state, font=FONTS["badge"], fill=text_col)


def draw_frame(state: str) -> Image.Image:
    img = _BASE.copy()

    # Character — centred horizontally, vertically centred
    char_x = (SCREEN_W - CHARACTER.width) // 2
    char_y = (SCREEN_H - CHARACTER.height) // 2
    img.paste(CHARACTER, (char_x, char_y), CHARACTER)

    draw = ImageDraw.Draw(img)

    # Clock — top left
    now = datetime.now()
    draw.text((32, 24),  now.strftime("%H:%M"),         font=FONTS["clock"], fill=TEXT_DARK)
    draw.text((36, 118), now.strftime("%a %d %b").upper(), font=FONTS["date"],  fill=TEXT_MID)

    # State badge — top right
    _draw_badge(draw, state)

    return img


# ---------------------------------------------------------------------------
# Main loop (standalone / demo)
# ---------------------------------------------------------------------------

_running = True

def _handle_sigint(sig, frame):
    global _running
    _running = False

signal.signal(signal.SIGINT, _handle_sigint)


def main():
    frame_time    = 1.0 / FPS
    state_duration = FPS * 3
    tick = 0

    if _PREVIEW:
        print("CarPi UI v2  |  PC preview mode")
        print("Close the window or Ctrl+C to quit")
        # Let tkinter close properly
        _root.protocol("WM_DELETE_WINDOW", lambda: globals().update(_running=False))
    else:
        print("CarPi UI v2  |  Pi framebuffer mode — Ctrl+C to quit")

    while _running:
        t0 = time.perf_counter()

        state = STATES[(tick // state_duration) % len(STATES)]
        img = draw_frame(state)
        show_frame(img)

        tick += 1
        elapsed = time.perf_counter() - t0
        sleep = frame_time - elapsed
        if sleep > 0:
            time.sleep(sleep)

    if not _PREVIEW:
        _fb.seek(0)
        _fb.write(bytes(SCREEN_W * SCREEN_H * 4))
        _fb.close()

    print("Done.")


if __name__ == "__main__":
    main()
