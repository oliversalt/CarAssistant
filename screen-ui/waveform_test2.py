import math
import random
import time
import numpy as np
import signal
import sys

# this one works but just uses numpy to draw instead of pygame becuase pygame doesn't work apparently

# --- Config ---
SCREEN_W = 800
SCREEN_H = 480
FPS = 30
NUM_BARS = 30
BG_COLOR = (0, 0, 0)        # RGB
BAR_COLOR = (0, 200, 255)   # RGB

running = True

def signal_handler(sig, frame):
    global running
    running = False

signal.signal(signal.SIGINT, signal_handler)

def draw_rect(frame, x, y, w, h, color):
    """Draw a filled rectangle onto the numpy frame buffer."""
    b, g, r = color[2], color[1], color[0]
    x1 = max(0, x)
    x2 = min(SCREEN_W, x + w)
    y1 = max(0, y)
    y2 = min(SCREEN_H, y + h)
    frame[y1:y2, x1:x2, 0] = b
    frame[y1:y2, x1:x2, 1] = g
    frame[y1:y2, x1:x2, 2] = r
    frame[y1:y2, x1:x2, 3] = 255

def main():
    fb = open('/dev/fb0', 'wb')
    tick = 0
    frame_time = 1.0 / FPS

    print("Running waveform animation. Press Ctrl+C to stop.")

    while running:
        start = time.time()

        # Create blank frame (BGRA format)
        frame = np.zeros((SCREEN_H, SCREEN_W, 4), dtype=np.uint8)

        bar_width = SCREEN_W // NUM_BARS
        padding = 4

        for i in range(NUM_BARS):
            phase = (i / NUM_BARS) * math.pi * 2
            wave = math.sin(tick * 0.08 + phase)
            noise = random.uniform(-0.1, 0.1)
            height = int(((wave + noise + 1) / 2) * (SCREEN_H * 0.7)) + 20

            x = i * bar_width + padding // 2
            y = (SCREEN_H - height) // 2
            w = bar_width - padding

            brightness = int(150 + (height / SCREEN_H) * 105)
            brightness = min(255, brightness)
            color = (0, brightness, 255)  # RGB

            draw_rect(frame, x, y, w, height, color)

        fb.seek(0)
        fb.write(frame.tobytes())
        fb.flush()

        tick += 1
        elapsed = time.time() - start
        sleep_time = frame_time - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Clear screen on exit
    fb.seek(0)
    fb.write(bytes(SCREEN_W * SCREEN_H * 4))
    fb.close()
    print("Done.")

if __name__ == "__main__":
    main()