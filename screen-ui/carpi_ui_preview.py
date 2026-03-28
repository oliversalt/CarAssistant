"""
CarPi UI - PC Preview
Renders the CarPi interface in a pygame window on your PC.
Same Pillow rendering code as the Pi framebuffer version.
Press 1/2/3/4 to switch states. Q to quit.
"""

import math
import time
import signal
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import pygame

# --- Config ---
SCREEN_W = 800
SCREEN_H = 480
FPS = 60

# Palette - stark monochrome with one warm accent
BG          = (8, 8, 8)
WHITE       = (255, 255, 255)
OFF_WHITE   = (235, 235, 228)
DIM         = (55, 55, 52)
MID         = (120, 120, 115)
SUBTLE      = (22, 22, 20)
ACCENT      = (255, 210, 80)   # warm amber — single colour pop

STATES = ["IDLE", "LISTENING", "THINKING", "SPEAKING"]
STATE_LABELS = {
    "IDLE":      "READY",
    "LISTENING": "LISTENING",
    "THINKING":  "THINKING",
    "SPEAKING":  "SPEAKING",
}


def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()


def get_fonts():
    # Try fonts available on both Windows and Pi
    candidates = [
        "C:/Windows/Fonts/bahnschrift.ttf",         # Windows — geometric sans
        "C:/Windows/Fonts/segoeui.ttf",              # Windows fallback
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",   # Pi
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    bold_candidates = [
        "C:/Windows/Fonts/bahnschrift.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]

    def first(paths, size):
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except:
                continue
        return ImageFont.load_default()

    return {
        "huge":   first(bold_candidates, 96),
        "big":    first(bold_candidates, 52),
        "mid":    first(candidates, 26),
        "small":  first(candidates, 18),
        "tiny":   first(candidates, 13),
    }


# ─── Animations ────────────────────────────────────────────────────────────────

def draw_idle(draw, tick):
    """Large breathing ring with inner pulse dot. Centred, uses full height."""
    cx, cy = SCREEN_W // 2, SCREEN_H // 2 + 20
    breath = (math.sin(tick * 0.025) + 1) / 2

    # Outer ring — fades in and out
    r_outer = int(105 + breath * 18)
    alpha_outer = int(35 + breath * 55)
    c = (alpha_outer, alpha_outer, alpha_outer - 5)
    draw.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
                 outline=c, width=1)

    # Middle ring
    r_mid = int(72 + breath * 10)
    alpha_mid = int(80 + breath * 100)
    c2 = (alpha_mid, alpha_mid, alpha_mid - 8)
    draw.ellipse([cx - r_mid, cy - r_mid, cx + r_mid, cy + r_mid],
                 outline=c2, width=2)

    # Inner filled circle
    r_inner = int(18 + breath * 10)
    alpha_inner = int(160 + breath * 95)
    c3 = (alpha_inner, alpha_inner, alpha_inner - 10)
    draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
                 fill=c3)

    # Four cardinal tick marks
    for angle in [0, 90, 180, 270]:
        rad = math.radians(angle)
        x1 = cx + (r_outer + 8) * math.cos(rad)
        y1 = cy + (r_outer + 8) * math.sin(rad)
        x2 = cx + (r_outer + 18) * math.cos(rad)
        y2 = cy + (r_outer + 18) * math.sin(rad)
        draw.line([(x1, y1), (x2, y2)], fill=(50, 50, 48), width=1)


def draw_listening(draw, tick):
    """Full-width waveform bars, tall, using most of the screen height."""
    cx = SCREEN_W // 2
    cy = SCREEN_H // 2 + 20
    num_bars = 40
    bar_w = 10
    gap = 8
    total = num_bars * (bar_w + gap) - gap
    start_x = cx - total // 2
    max_h = 180

    for i in range(num_bars):
        phase = (i / num_bars) * math.pi * 2
        wave = math.sin(tick * 0.1 + phase)
        wave2 = math.sin(tick * 0.07 + phase * 1.3) * 0.4
        combined = (wave + wave2) / 1.4
        bar_h = int(((combined + 1) / 2) * max_h) + 12

        x = start_x + i * (bar_w + gap)
        y = cy - bar_h // 2

        # Amber accent on centre bars, white on others
        centre_dist = abs(i - num_bars // 2) / (num_bars // 2)
        if centre_dist < 0.2:
            r, g, b = ACCENT
        else:
            v = int(180 + (1 - centre_dist) * 75)
            r, g, b = v, v, v - 8

        draw.rounded_rectangle([x, y, x + bar_w, y + bar_h],
                                radius=3, fill=(r, g, b))


def draw_thinking(draw, tick):
    """Two counter-rotating arcs with a central amber dot."""
    cx, cy = SCREEN_W // 2, SCREEN_H // 2 + 20

    for ring_i, (radius, arc_len, speed_mul, width, rev) in enumerate([
        (90,  220, 1.0,  3, False),
        (62,  160, 1.6,  2, True),
    ]):
        direction = -1 if rev else 1
        start_angle = (tick * 3.5 * speed_mul * direction) % 360
        steps = 50

        for s in range(steps):
            t = start_angle + (arc_len * s / steps)
            t_next = start_angle + (arc_len * (s + 1) / steps)
            rad  = math.radians(t)
            rad2 = math.radians(t_next)
            x1 = cx + radius * math.cos(rad)
            y1 = cy + radius * math.sin(rad)
            x2 = cx + radius * math.cos(rad2)
            y2 = cy + radius * math.sin(rad2)

            fade = s / steps
            if ring_i == 0:
                alpha = int(40 + fade * 215)
                color = (alpha, alpha, alpha - 5)
            else:
                alpha = int(30 + fade * 180)
                color = (alpha, alpha, alpha)

            draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

        # Leading dot
        end_rad = math.radians(start_angle + arc_len)
        lx = cx + radius * math.cos(end_rad)
        ly = cy + radius * math.sin(end_rad)
        draw.ellipse([lx - 3, ly - 3, lx + 3, ly + 3], fill=WHITE)

    # Centre amber dot pulses
    pulse = (math.sin(tick * 0.12) + 1) / 2
    r_dot = int(7 + pulse * 5)
    draw.ellipse([cx - r_dot, cy - r_dot, cx + r_dot, cy + r_dot], fill=ACCENT)


def draw_speaking(draw, tick):
    """Rings expanding outward with amber centre."""
    cx, cy = SCREEN_W // 2, SCREEN_H // 2 + 20
    num_rings = 6
    speed = 0.035

    for i in range(num_rings):
        offset = i / num_rings
        phase = ((tick * speed) + offset) % 1.0
        radius = int(phase * 190) + 8
        alpha = int((1 - phase) ** 1.4 * 220)
        if alpha < 6:
            continue
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     outline=(alpha, alpha, alpha - 5), width=2)

    # Amber core
    pulse = (math.sin(tick * 0.15) + 1) / 2
    r_core = int(10 + pulse * 6)
    draw.ellipse([cx - r_core, cy - r_core, cx + r_core, cy + r_core],
                 fill=ACCENT)


# ─── Frame builder ──────────────────────────────────────────────────────────────

def draw_frame(tick, state, fonts):
    img = Image.new("RGBA", (SCREEN_W, SCREEN_H), BG + (255,))
    draw = ImageDraw.Draw(img)

    # Subtle vertical rule on left edge
    draw.rectangle([0, 0, 2, SCREEN_H], fill=SUBTLE)

    # ── Top bar ──────────────────────────────────────────────────────────────
    # Time — large, left
    now = datetime.now()
    time_str = now.strftime("%H:%M")
    draw.text((28, 18), time_str, font=fonts["big"], fill=OFF_WHITE)

    # Date — small, below time
    date_str = now.strftime("%A  %d %B").upper()
    draw.text((30, 82), date_str, font=fonts["tiny"], fill=MID)

    # State label — large, right aligned, vertically centred in top bar
    label = STATE_LABELS[state]
    bbox = draw.textbbox((0, 0), label, font=fonts["mid"])
    lw = bbox[2] - bbox[0]
    lh = bbox[3] - bbox[1]
    # Amber accent bar behind state label
    pad = 10
    label_x = SCREEN_W - 28 - lw
    label_y = 40
    draw.rectangle(
        [label_x - pad, label_y - 6, label_x + lw + pad, label_y + lh + 6],
        fill=SUBTLE
    )
    draw.text((label_x, label_y), label, font=fonts["mid"], fill=ACCENT)

    # Divider
    draw.rectangle([28, 112, SCREEN_W - 28, 113], fill=DIM)

    # ── Centre animation ──────────────────────────────────────────────────────
    if state == "IDLE":
        draw_idle(draw, tick)
    elif state == "LISTENING":
        draw_listening(draw, tick)
    elif state == "THINKING":
        draw_thinking(draw, tick)
    elif state == "SPEAKING":
        draw_speaking(draw, tick)

    # ── Bottom bar ────────────────────────────────────────────────────────────
    draw.rectangle([28, SCREEN_H - 50, SCREEN_W - 28, SCREEN_H - 49], fill=DIM)

    # CarPi wordmark
    draw.text((30, SCREEN_H - 38), "CARPI", font=fonts["tiny"], fill=MID)

    # State progress dots — right side
    dot_r = 4
    dot_gap = 16
    total_dots = len(STATES) * dot_gap
    dot_start_x = SCREEN_W - 28 - total_dots
    dot_y = SCREEN_H - 32

    for i, s in enumerate(STATES):
        dx = dot_start_x + i * dot_gap
        if s == state:
            # Active — amber filled
            draw.ellipse([dx - dot_r, dot_y - dot_r, dx + dot_r, dot_y + dot_r],
                         fill=ACCENT)
        else:
            # Inactive — dim outline
            draw.ellipse([dx - dot_r, dot_y - dot_r, dx + dot_r, dot_y + dot_r],
                         outline=DIM, width=1)

    return img


# ─── Main ───────────────────────────────────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("CarPi UI Preview")
    clock = pygame.time.Clock()

    fonts = get_fonts()

    tick = 0
    state_index = 0
    state = STATES[state_index]
    auto_cycle = True
    state_duration = FPS * 5  # auto-cycle every 5 seconds

    print("CarPi UI Preview")
    print("Press 1/2/3/4 to switch states manually")
    print("Press A to toggle auto-cycle")
    print("Press Q to quit")

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_1:
                    state = "IDLE";      auto_cycle = False
                if event.key == pygame.K_2:
                    state = "LISTENING"; auto_cycle = False
                if event.key == pygame.K_3:
                    state = "THINKING";  auto_cycle = False
                if event.key == pygame.K_4:
                    state = "SPEAKING";  auto_cycle = False
                if event.key == pygame.K_a:
                    auto_cycle = not auto_cycle
                    print(f"Auto-cycle: {'on' if auto_cycle else 'off'}")

        if auto_cycle:
            state = STATES[(tick // state_duration) % len(STATES)]

        # Render via Pillow
        img = draw_frame(tick, state, fonts)

        # Convert to pygame surface
        raw = img.tobytes("raw", "RGBA")
        surf = pygame.image.frombuffer(raw, (SCREEN_W, SCREEN_H), "RGBA")
        screen.blit(surf, (0, 0))
        pygame.display.flip()

        tick += 1
        clock.tick(FPS)


if __name__ == "__main__":
    main()