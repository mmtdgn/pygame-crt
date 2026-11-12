"""Asset-free interactive demo: python -m pygame_crt.demo."""

from __future__ import annotations

import argparse
import math
import os
import statistics
import time
from pathlib import Path

import pygame

from .filter import CRTFilter

SOURCE_SIZE = (640, 400)
BACKGROUND = (9, 14, 29)
CYAN = (85, 230, 235)
GOLD = (255, 198, 107)


class Scene:
    """Procedural starfield, moving ship, and clickable target; no game assets."""

    button = pygame.Rect(476, 58, 136, 32)

    def __init__(self):
        self.font = pygame.font.Font(None, 22)
        self.small = pygame.font.Font(None, 17)
        self.title = pygame.font.Font(None, 36)
        self.ship = pygame.Vector2(320, 230)
        self.target = pygame.Vector2(470, 180)
        self.hits = 0
        self.seconds = 0.0
        self.paused = False

    def update(self, dt: float, keys) -> None:
        if self.paused:
            return
        self.seconds += dt
        direction = pygame.Vector2(
            int(keys[pygame.K_d] or keys[pygame.K_RIGHT])
            - int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
            int(keys[pygame.K_s] or keys[pygame.K_DOWN])
            - int(keys[pygame.K_w] or keys[pygame.K_UP]),
        )
        if direction.length_squared():
            self.ship += direction.normalize() * 150 * dt
        self.ship.x = max(28, min(612, self.ship.x))
        self.ship.y = max(120, min(300, self.ship.y))

    def click(self, point) -> None:
        if point is None:
            return
        if self.button.collidepoint(point):
            self.hits += 1
        elif 105 < point[1] < 315:
            self.target.update(point)

    def draw(self, surface: pygame.Surface, crt: CRTFilter) -> None:
        surface.fill(BACKGROUND)
        t = self.seconds
        for i in range(90):
            x = (i * 137.3 - t * (8 + i % 4 * 7)) % 640
            y = 106 + (i * 73.7) % 204
            color = (45 + i % 4 * 20, 65 + i % 4 * 20, 100 + i % 4 * 20)
            pygame.draw.rect(surface, color, (round(x), round(y), 2, 2))
        for x in range(16, 640, 32):
            pygame.draw.line(surface, (17, 34, 48), (x, 108), (x, 312))
        for y in range(120, 313, 32):
            pygame.draw.line(surface, (17, 34, 48), (16, y), (624, y))
        pygame.draw.rect(surface, (44, 74, 92), (16, 105, 608, 211), 1)

        def label(text, pos, color=CYAN, font=None):
            surface.blit((font or self.font).render(text, True, color), pos)

        label("PYGAME / CRT", (26, 19), font=self.title)
        label("SOFTWARE GLASS  //  LIVE SIGNAL", (28, 52), (132, 153, 177), self.small)
        label("NO SHADERS. JUST PIXELS.", (28, 76), (132, 153, 177), self.small)
        label("SIGNAL " + ("CRT" if crt.enabled else "CLEAN"), (486, 25), GOLD)
        pygame.draw.rect(surface, (21, 47, 59), self.button, border_radius=5)
        pygame.draw.rect(surface, CYAN, self.button, 1, border_radius=5)
        label(f"CLICK TEST: {self.hits:02}", (489, 67), CYAN, self.small)

        tx, ty = round(self.target.x), round(self.target.y)
        radius = 12 + round(2 * math.sin(t * 4))
        pygame.draw.circle(surface, GOLD, (tx, ty), radius, 1)
        pygame.draw.line(surface, GOLD, (tx - 18, ty), (tx - 8, ty))
        pygame.draw.line(surface, GOLD, (tx + 8, ty), (tx + 18, ty))
        pygame.draw.line(surface, GOLD, (tx, ty - 18), (tx, ty - 8))
        pygame.draw.line(surface, GOLD, (tx, ty + 8), (tx, ty + 18))
        label("CLICK TO AIM", (tx - 37, ty + 24), GOLD, self.small)

        sx, sy = round(self.ship.x), round(self.ship.y + math.sin(t * 3) * 3)
        flame = 11 + round(5 * math.sin(t * 20))
        pygame.draw.polygon(
            surface, (255, 116, 79), [(sx - 17, sy - 5), (sx - 17 - flame, sy), (sx - 17, sy + 5)]
        )
        pygame.draw.polygon(
            surface, CYAN, [(sx + 22, sy), (sx - 18, sy - 13), (sx - 10, sy), (sx - 18, sy + 13)]
        )
        pygame.draw.polygon(
            surface, (235, 255, 255), [(sx + 12, sy), (sx - 7, sy - 5), (sx - 5, sy + 5)]
        )
        label("SPACE COURIER", (26, 114), (132, 153, 177), self.small)

        c = crt.config
        label(
            f"F1 CRT {'ON' if crt.enabled else 'OFF'}    "
            f"F2 SCANLINES {'ON' if c.scanlines else 'OFF'}    "
            f"F3 BLOOM {'ON' if c.bloom else 'OFF'}    "
            f"F4 BEZEL {'ON' if c.bezel else 'OFF'}",
            (26, 331),
            CYAN,
            self.small,
        )
        label(
            "WASD / ARROWS move    CLICK aim    SPACE pause    ESC quit",
            (26, 353),
            (157, 173, 193),
            self.small,
        )
        label(
            f"[ / ] curvature {c.curvature_x:.3f}, {c.curvature_y:.3f}"
            + ("    PAUSED" if self.paused else "    RESIZE THE WINDOW"),
            (26, 375),
            GOLD,
            self.small,
        )


def handle_event(event, scene: Scene, crt: CRTFilter, viewport: pygame.Rect) -> bool:
    """Return False on quit; consume mouse event positions through the CRT map."""
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        scene.click(crt.map_to_source(event.pos, SOURCE_SIZE, viewport))
    if event.type == pygame.KEYDOWN:
        key = event.key
        if key == pygame.K_ESCAPE:
            return False
        if key == pygame.K_F1:
            crt.enabled = not crt.enabled
        elif key == pygame.K_F2:
            crt.configure(scanlines=not crt.config.scanlines)
        elif key == pygame.K_F3:
            crt.configure(bloom=not crt.config.bloom)
        elif key == pygame.K_F4:
            crt.configure(bezel=not crt.config.bezel)
        elif key == pygame.K_SPACE:
            scene.paused = not scene.paused
        elif key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
            delta = 0.01 if key == pygame.K_RIGHTBRACKET else -0.01
            crt.configure(
                curvature_x=max(0, min(0.5, crt.config.curvature_x + delta)),
                curvature_y=max(0, min(0.5, crt.config.curvature_y + delta)),
            )
    return True


def comparison(path: Path, scene: Scene, source: pygame.Surface) -> None:
    """Save a reproducible still made entirely from the bundled demo."""
    scene.seconds = 1.5
    crt = CRTFilter()
    scene.draw(source, crt)
    output = pygame.Surface((1280, 448))
    output.fill(BACKGROUND)
    clean = CRTFilter(enabled=False)
    clean.render(source, output, pygame.Rect(0, 48, 640, 400))
    crt.render(source, output, pygame.Rect(640, 48, 640, 400))
    for text, x in (("ORIGINAL FRAME", 26), ("PYGAME-CRT", 666)):
        output.blit(scene.font.render(text, True, CYAN), (x, 18))
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(output, str(path))


def benchmark(samples: int = 30) -> None:
    import json
    import platform

    results = []
    source = pygame.Surface(SOURCE_SIZE)
    scene = Scene()
    crt = CRTFilter()
    scene.draw(source, crt)
    for size in ((640, 400), (1280, 720), (1920, 1080)):
        target = pygame.Surface(size)
        crt.render(source, target)  # warm caches before measurement
        timings = []
        for _ in range(samples):
            start = time.perf_counter()
            crt.render(source, target)
            timings.append((time.perf_counter() - start) * 1000)
        results.append(
            {
                "size": list(size),
                "median_ms": round(statistics.median(timings), 3),
                "max_ms": round(max(timings), 3),
            }
        )
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "pygame": pygame.version.ver,
                "pygame_ce": bool(getattr(pygame, "IS_CE", False)),
                "samples": samples,
                "scope": "render: scaling, CRT and bezel; no flip",
                "bloom": False,
                "results": results,
            },
            indent=2,
        )
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true", help="use SDL's dummy display")
    parser.add_argument(
        "--frames", type=int, default=0, help="exit after N frames (0: interactive)"
    )
    parser.add_argument("--screenshot", type=Path, help="save the final demo frame as PNG")
    parser.add_argument("--comparison", type=Path, help="save a before/after PNG and exit")
    parser.add_argument("--benchmark", action="store_true", help="print warm-cache CPU timings")
    args = parser.parse_args(argv)
    if args.frames < 0:
        parser.error("--frames must be non-negative")
    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        if not args.frames:
            args.frames = 3
    pygame.display.init()
    pygame.font.init()
    try:
        window = pygame.display.set_mode((960, 600), pygame.RESIZABLE)
        pygame.display.set_caption("pygame-crt | F1 compare | F2 scanlines | F3 bloom | F4 bezel")
        source = pygame.Surface(SOURCE_SIZE)
        scene, crt = Scene(), CRTFilter()
        if args.comparison:
            comparison(args.comparison, scene, source)
            return 0
        if args.benchmark:
            benchmark()
            return 0
        clock = pygame.time.Clock()
        running, count = True, 0
        while running:
            dt = 1 / 60 if args.headless else min(clock.tick(60) / 1000, 0.05)
            for event in pygame.event.get():
                view = crt.viewport(SOURCE_SIZE, window.get_rect())
                if not handle_event(event, scene, crt, view):
                    running = False
                    break
            if not running:
                break
            scene.update(dt, pygame.key.get_pressed())
            scene.draw(source, crt)
            crt.render(source, window)
            pygame.display.flip()
            count += 1
            if args.frames and count >= args.frames:
                running = False
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(window, str(args.screenshot))
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
