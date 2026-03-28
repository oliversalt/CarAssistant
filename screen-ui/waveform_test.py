import pygame
import math
import random
import sys
import os

# Required for Pi OS Lite (no desktop)
# os.environ['SDL_VIDEODRIVER'] = 'fbcon'
# os.environ['SDL_FBDEV'] = '/dev/fb0'

# --- Config ---
SCREEN_W = 800
SCREEN_H = 480
FPS = 60
NUM_BARS = 30
BAR_COLOR = (0, 200, 255)
BG_COLOR = (0, 0, 0)

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Waveform Test")
    clock = pygame.time.Clock()

    tick = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    pygame.quit()
                    sys.exit()

        screen.fill(BG_COLOR)

        bar_width = SCREEN_W // NUM_BARS
        padding = 4

        for i in range(NUM_BARS):
            # Each bar uses a sine wave offset by its position, giving a ripple effect
            phase = (i / NUM_BARS) * math.pi * 2
            wave = math.sin(tick * 0.05 + phase)
            # Add a bit of randomness for a more organic feel
            noise = random.uniform(-0.1, 0.1)
            height = int(((wave + noise + 1) / 2) * (SCREEN_H * 0.7)) + 20

            x = i * bar_width + padding // 2
            y = (SCREEN_H - height) // 2
            w = bar_width - padding

            # Tint colour slightly based on height for visual depth
            brightness = int(150 + (height / SCREEN_H) * 100)
            color = (0, brightness, 255)

            pygame.draw.rect(screen, color, (x, y, w, height), border_radius=4)

        pygame.display.flip()
        tick += 1
        clock.tick(FPS)

if __name__ == "__main__":
    main()
