"""
CarPi UI v2 - PC Preview
White background, character image, clock, state badge.
Press 1-6 to switch states. Q to quit.

States: READY, LISTENING, THINKING, SPEAKING, NO WIFI, ERROR
"""

import sys
import time
import math
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import pygame

# --- Config ---
SCREEN_W = 800
SCREEN_H = 480
FPS = 60

# Palette
BG          = (255, 255, 255)
TEXT_DARK   = (20, 20, 20)
TEXT_MID    = (140, 140, 140)

# State badge colours (fill, text)
BADGE_COLOURS = {
    "READY":     ((230, 255, 235), (30, 160, 60)),
    "LISTENING": ((255, 248, 225), (200, 140, 0)),
    "THINKING":  ((235, 235, 255), (70, 70, 220)),
    "SPEAKING":  ((225, 248, 255), (0, 150, 190)),
    "NO WIFI":   ((255, 238, 230), (210, 80, 30)),
    "ERROR":     ((255, 230, 230), (200, 30, 30)),
}

STATES = ["READY", "LISTENING", "THINKING", "SPEAKING", "NO WIFI", "ERROR"]

CHARACTER_PATH = Path(__file__).parent.parent / "animation" / "salty.png"
CHARACTER_HEIGHT = 480  # px — scale the image to this height


def load_font(candidates, size):
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def get_fonts():
    regular = [
        "C:/Windows/Fonts/bahnschrift.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    bold = [
        "C:/Windows/Fonts/bahnschrift.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    return {
        "clock":  load_font(bold,    86),
        "date":   load_font(regular, 18),
        "badge":  load_font(bold,    40),
    }


def load_character(height: int) -> Image.Image:
    img = Image.open(CHARACTER_PATH).convert("RGBA")
    aspect = img.width / img.height
    w = int(height * aspect)
    return img.resize((w, height), Image.LANCZOS)


def draw_badge(draw: ImageDraw.Draw, state: str, fonts: dict, x: int, y: int):
    """Draw a rounded-rectangle badge at (x, y) — right-aligned from x."""
    fill, text_col = BADGE_COLOURS[state]
    pad_x, pad_y = 35, 20
    bbox = draw.textbbox((0, 0), state, font=fonts["badge"])
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    bw = tw + pad_x * 2
    bh = th + pad_y * 2
    bx = x - bw  # right-align
    by = y
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=fill)
    draw.text((bx + pad_x, by + pad_y), state, font=fonts["badge"], fill=text_col)


def draw_frame(
    img_base: Image.Image,
    character: Image.Image,
    tick: int,
    state: str,
    fonts: dict,
) -> Image.Image:
    img = img_base.copy()
    draw = ImageDraw.Draw(img)

    # ── Character — centred horizontally, slightly below vertical centre ──────
    char_x = (SCREEN_W - character.width) // 2
    char_y = SCREEN_H // 2 - character.height // 2 + 0 #shift down 0 pixels
    img.paste(character, (char_x, char_y), character)

    # ── Clock — top left ──────────────────────────────────────────────────────
    now = datetime.now()
    time_str = now.strftime("%H:%M")
    draw.text((32, 24), time_str, font=fonts["clock"], fill=TEXT_DARK)

    date_str = now.strftime("%a %d %b").upper()
    draw.text((36, 118), date_str, font=fonts["date"], fill=TEXT_MID)

    # ── State badge — top right ───────────────────────────────────────────────
    draw_badge(draw, state, fonts, SCREEN_W - 32, 36)

    return img


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("CarPi UI v2 Preview")
    clock = pygame.time.Clock()

    fonts = get_fonts()
    character = load_character(CHARACTER_HEIGHT)

    # Pre-build a white base image
    base = Image.new("RGBA", (SCREEN_W, SCREEN_H), BG + (255,))

    tick = 0
    state_index = 0
    state = STATES[state_index]
    auto_cycle = True
    state_duration = FPS * 3  # auto-cycle every 3 seconds

    print("CarPi UI v2 Preview")
    print("Press 1-6 to switch states  |  A to toggle auto-cycle  |  Q to quit")
    for i, s in enumerate(STATES, 1):
        print(f"  {i}: {s}")

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_a:
                    auto_cycle = not auto_cycle
                    print(f"Auto-cycle: {'on' if auto_cycle else 'off'}")
                for i, s in enumerate(STATES):
                    if event.key == getattr(pygame, f"K_{i + 1}", None):
                        state = s
                        auto_cycle = False

        if auto_cycle:
            state = STATES[(tick // state_duration) % len(STATES)]

        img = draw_frame(base, character, tick, state, fonts)

        raw = img.tobytes("raw", "RGBA")
        surf = pygame.image.frombuffer(raw, (SCREEN_W, SCREEN_H), "RGBA")
        screen.blit(surf, (0, 0))
        pygame.display.flip()

        tick += 1
        clock.tick(FPS)


if __name__ == "__main__":
    main()
