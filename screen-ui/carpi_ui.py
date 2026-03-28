import math
import time
import signal
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# --- Config ---
SCREEN_W = 800
SCREEN_H = 480
FPS = 30

# Colours (RGB)
BG        = (10, 10, 10)
WHITE     = (255, 255, 255)
DIM       = (80, 80, 80)
MID       = (160, 160, 160)
ACCENT    = (220, 220, 220)

# States cycle automatically for demo — replace with your state machine later
STATES = ["IDLE", "LISTENING", "THINKING", "SPEAKING"]
STATE_LABELS = {
    "IDLE":      "Ready",
    "LISTENING": "Listening",
    "THINKING":  "Thinking",
    "SPEAKING":  "Speaking",
}

running = True

def signal_handler(sig, frame):
    global running
    running = False

signal.signal(signal.SIGINT, signal_handler)


def load_font(size):
    """Try to load a clean system font, fall back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()


def draw_idle(draw, tick, w, h):
    """Slow breathing circle."""
    cx, cy = w // 2, h // 2
    breath = (math.sin(tick * 0.03) + 1) / 2  # 0 to 1
    radius = int(60 + breath * 25)
    alpha = int(80 + breath * 120)
    color = (alpha, alpha, alpha)

    # Outer ring
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        outline=color, width=2
    )
    # Inner dot
    inner = int(6 + breath * 4)
    draw.ellipse(
        [cx - inner, cy - inner, cx + inner, cy + inner],
        fill=color
    )


def draw_listening(draw, tick, w, h):
    """Animated waveform bars."""
    cx = w // 2
    cy = h // 2
    num_bars = 24
    bar_w = 10
    gap = 6
    total = num_bars * (bar_w + gap)
    start_x = cx - total // 2

    for i in range(num_bars):
        phase = (i / num_bars) * math.pi * 2
        wave = math.sin(tick * 0.12 + phase)
        bar_h = int(((wave + 1) / 2) * 140) + 20
        x = start_x + i * (bar_w + gap)
        y = cy - bar_h // 2

        brightness = int(140 + (bar_h / 160) * 115)
        brightness = min(255, brightness)
        color = (brightness, brightness, brightness)

        draw.rounded_rectangle([x, y, x + bar_w, y + bar_h], radius=3, fill=color)


def draw_thinking(draw, tick, w, h):
    """Rotating arc spinner."""
    cx, cy = w // 2, h // 2
    radius = 70
    arc_length = 240  # degrees
    speed = tick * 4
    start_angle = speed % 360
    end_angle = (start_angle + arc_length) % 360

    # Draw arc manually with line segments
    steps = 60
    points = []
    for s in range(steps + 1):
        t = start_angle + (arc_length * s / steps)
        rad = math.radians(t)
        x = cx + radius * math.cos(rad)
        y = cy + radius * math.sin(rad)
        points.append((x, y))

    for i in range(len(points) - 1):
        # Fade along arc
        alpha = int(80 + (i / steps) * 175)
        color = (alpha, alpha, alpha)
        draw.line([points[i], points[i + 1]], fill=color, width=4)

    # Small leading dot
    lx, ly = points[-1]
    draw.ellipse([lx - 4, ly - 4, lx + 4, ly + 4], fill=WHITE)


def draw_speaking(draw, tick, w, h):
    """Radiating rings that pulse outward."""
    cx, cy = w // 2, h // 2
    num_rings = 4
    speed = 0.04

    for i in range(num_rings):
        offset = (i / num_rings)
        phase = ((tick * speed) + offset) % 1.0
        radius = int(phase * 160) + 10
        alpha = int((1 - phase) * 200)
        if alpha < 5:
            continue
        color = (alpha, alpha, alpha)
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            outline=color, width=2
        )


def draw_frame(tick, state, font_large, font_small, font_time):
    img = Image.new("RGBA", (SCREEN_W, SCREEN_H), BG + (255,))
    draw = ImageDraw.Draw(img)

    # --- Clock (top left) ---
    now = datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%a %d %b").upper()
    draw.text((40, 32), time_str, font=font_time, fill=WHITE)
    draw.text((40, 95), date_str, font=font_small, fill=DIM)

    # --- State label (top right) ---
    label = STATE_LABELS[state]
    bbox = draw.textbbox((0, 0), label, font=font_small)
    lw = bbox[2] - bbox[0]
    draw.text((SCREEN_W - 40 - lw, 46), label, font=font_small, fill=MID)

    # --- Divider lines ---
    draw.line([(40, 130), (SCREEN_W - 40, 130)], fill=(30, 30, 30), width=1)
    draw.line([(40, SCREEN_H - 80)  , (SCREEN_W - 40, SCREEN_H - 80)], fill=(30, 30, 30), width=1)

    # --- Central animation ---
    if state == "IDLE":
        draw_idle(draw, tick, SCREEN_W, SCREEN_H - 50)
    elif state == "LISTENING":
        draw_listening(draw, tick, SCREEN_W, SCREEN_H - 50)
    elif state == "THINKING":
        draw_thinking(draw, tick, SCREEN_W, SCREEN_H - 50)
    elif state == "SPEAKING":
        draw_speaking(draw, tick, SCREEN_W, SCREEN_H - 50)

    # --- Bottom status bar ---
    status_y = SCREEN_H - 60
    draw.text((40, status_y), "CarPi", font=font_small, fill=DIM)

    # State dots
    dot_x = SCREEN_W - 40 - (len(STATES) * 20)
    for s in STATES:
        color = WHITE if s == state else (40, 40, 40)
        draw.ellipse([dot_x, status_y + 8, dot_x + 10, status_y + 18], fill=color)
        dot_x += 20

    return img


def write_to_fb(fb, img):
    # Convert RGBA PIL image to BGRA bytes for framebuffer
    r, g, b, a = img.split()
    bgra = Image.merge("RGBA", (b, g, r, a))
    fb.seek(0)
    fb.write(bgra.tobytes())
    fb.flush()


def main():
    font_time  = load_font(52)
    font_large = load_font(36)
    font_small = load_font(20)

    fb = open('/dev/fb0', 'wb')
    tick = 0
    frame_time = 1.0 / FPS

    # Cycle states every 4 seconds for demo
    state_duration = 4 * FPS
    state_index = 0

    print("CarPi UI running. Ctrl+C to stop.")

    while running:
        start = time.time()

        # Cycle through states automatically (replace with real state machine)
        state_index_pos = tick // state_duration % len(STATES)
        state = STATES[state_index_pos]

        img = draw_frame(tick, state, font_large, font_small, font_time)
        write_to_fb(fb, img)

        tick += 1
        elapsed = time.time() - start
        sleep_time = frame_time - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Clear on exit
    fb.seek(0)
    fb.write(bytes(SCREEN_W * SCREEN_H * 4))
    fb.close()
    print("Done.")


if __name__ == "__main__":
    main()
