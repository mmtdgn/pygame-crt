"""Smallest integration: draw a fresh frame, apply the filter, then flip."""

import pygame

from pygame_crt import CRTFilter


def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
    pygame.display.set_caption("pygame-crt / minimal / Escape to close")
    clock = pygame.time.Clock()
    crt = CRTFilter()
    elapsed = 0
    running = True
    try:
        while running:
            elapsed += clock.tick(60) / 1000
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
                ):
                    running = False
            screen.fill((12, 18, 32))
            w, h = screen.get_size()
            for y in range(0, h, 32):
                pygame.draw.line(screen, (30, 70, 85), (0, y), (w, y))
            pygame.draw.circle(screen, (80, 240, 220), (int(elapsed * 130) % w, h // 2), 35)
            crt.apply(screen)
            pygame.display.flip()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
