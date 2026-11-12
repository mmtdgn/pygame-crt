"""Public behavior checks shared by Pygame and pygame-ce; no game dependency."""

import math
import os
import random
import subprocess
import sys
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame

from pygame_crt import CRTConfig, CRTFilter


def pixels(surface):
    return pygame.image.tobytes(surface, "RGBA")


def plain(**options):
    return CRTFilter(
        curvature_x=0,
        curvature_y=0,
        scanlines=False,
        phosphor=False,
        vignette=False,
        bezel=False,
        **options,
    )


class FilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_import_does_not_initialize_pygame_or_create_window(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import pygame_crt, pygame; "
                "assert not pygame.get_init(); assert pygame.display.get_surface() is None",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_disabled_is_pixel_exact_and_returns_input(self):
        surface = pygame.Surface((173, 111), pygame.SRCALPHA)
        surface.fill((21, 70, 120, 91))
        before = pixels(surface)
        self.assertIs(CRTFilter(enabled=False).apply(surface), surface)
        self.assertEqual(before, pixels(surface))

    def test_zero_effects_preserve_rgb(self):
        surface = pygame.Surface((75, 47))
        surface.fill((42, 97, 161))
        pygame.draw.line(surface, (200, 30, 0), (0, 0), (74, 46))
        before = pixels(surface)
        plain().apply(surface)
        self.assertEqual(before, pixels(surface))

    def test_scanline_pitch_and_opacity(self):
        surface = pygame.Surface((31, 22))
        surface.fill((180, 180, 180))
        crt = plain()
        crt.configure(scanlines=True, scanline_spacing=4, scanline_alpha=128)
        crt.apply(surface)
        self.assertLess(surface.get_at((5, 4)).r, 100)
        self.assertEqual(surface.get_at((5, 5)).r, 180)

    def test_vignette_darkens_edges_without_washing_center(self):
        surface = pygame.Surface((200, 140))
        surface.fill((180, 180, 180))
        crt = plain()
        crt.configure(vignette=True, vignette_alpha=160)
        crt.apply(surface)
        self.assertGreater(surface.get_at((100, 70)).r, 175)
        self.assertLess(surface.get_at((0, 0)).r, 100)

    def test_bloom_keeps_black_black_and_spreads_highlights(self):
        crt = plain(bloom=True, bloom_strength=1, bloom_threshold=100)
        black = pygame.Surface((64, 64))
        crt.apply(black)
        self.assertEqual(black.get_at((32, 32))[:3], (0, 0, 0))
        pygame.draw.rect(black, (250, 250, 250), (24, 24, 16, 16))
        crt.apply(black)
        self.assertGreater(black.get_at((23, 32)).r, 0)
        self.assertEqual(black.get_at((0, 0)).r, 0)

    def test_alpha_is_flattened_on_background(self):
        surface = pygame.Surface((32, 32), pygame.SRCALPHA)
        surface.fill((240, 10, 10, 0))
        crt = plain(background=(7, 17, 27))
        crt.apply(surface)
        self.assertEqual(surface.get_at((16, 16)), (7, 17, 27, 255))

    def test_24_and_32_bit_surfaces(self):
        for depth in (24, 32):
            with self.subTest(depth=depth):
                source = pygame.Surface((81, 57), depth=depth)
                source.fill((70, 130, 200))
                target = pygame.Surface((160, 120), depth=depth)
                CRTFilter().render(source, target)
                self.assertGreater(target.get_at(target.get_rect().center).b, 100)

    def test_render_composites_transparency_once_on_reused_buffer(self):
        for kind in ("pixel_alpha", "surface_alpha", "colorkey"):
            for enabled in (True, False):
                with self.subTest(kind=kind, enabled=enabled):
                    source = pygame.Surface(
                        (20, 20), pygame.SRCALPHA if kind == "pixel_alpha" else 0
                    )
                    source.fill((240, 10, 10, 0) if kind == "pixel_alpha" else (240, 10, 10))
                    if kind == "surface_alpha":
                        source.set_alpha(128)
                    if kind == "colorkey":
                        source.set_colorkey((240, 10, 10))
                    expected = pygame.Surface((20, 20))
                    expected.fill((7, 17, 27))
                    expected.blit(source, (0, 0))
                    before = pixels(source)
                    crt = plain(enabled=enabled, background=(7, 17, 27))
                    for _ in range(2):
                        target = pygame.Surface((40, 40))
                        crt.render(source, target)
                        self.assertEqual(target.get_at((20, 20)), expected.get_at((10, 10)))
                    self.assertEqual(pixels(source), before)

    def test_invalid_surfaces_raise_useful_errors(self):
        for depth in (8, 16):
            with self.assertRaisesRegex(ValueError, "24-bit or 32-bit"):
                CRTFilter().apply(pygame.Surface((10, 10), depth=depth))
        surface = pygame.Surface((10, 10))
        surface.lock()
        try:
            with self.assertRaisesRegex(ValueError, "Unlock"):
                CRTFilter().apply(surface)
        finally:
            surface.unlock()
        with self.assertRaisesRegex(ValueError, "positive integers"):
            CRTFilter().apply(pygame.Surface((0, 10)))

    def test_resize_and_tiny_frames(self):
        crt = CRTFilter(bloom=True)
        for size in ((1, 1), (2, 3), (1, 12), (11, 1), (17, 29), (160, 90), (90, 160)):
            with self.subTest(size=size):
                surface = pygame.Surface(size)
                surface.fill((120, 180, 220))
                crt.apply(surface)
                target = pygame.Surface(size)
                viewport = crt.render(surface, target)
                self.assertTrue(target.get_rect().contains(viewport))

    def test_settings_changes_take_effect_and_failed_change_is_atomic(self):
        crt = plain()
        surface = pygame.Surface((100, 80))
        surface.fill((200, 200, 200))
        crt.apply(surface)
        before = pixels(surface)
        crt.configure(scanlines=True, scanline_alpha=200)
        crt.apply(surface)
        self.assertNotEqual(pixels(surface), before)
        config = crt.config
        with self.assertRaises(ValueError):
            crt.configure(curvature_x=-1, scanlines=False)
        self.assertEqual(crt.config, config)

    def test_config_validation(self):
        for values in (
            {"curvature_x": float("nan")},
            {"curvature_y": float("inf")},
            {"curvature_x": -0.1},
            {"scanline_alpha": 256},
            {"scanlines": 1},
            {"scanline_spacing": 1.5},
            {"bloom_strength": 2},
            {"bezel_ratio": 0.3},
            {"background": [0, 0, 0]},
            {"background": (0, -1, 0)},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                CRTConfig(**values)

    def test_repeated_fresh_frames_are_deterministic(self):
        crt = CRTFilter(bloom=True)
        original = pygame.Surface((123, 87))
        original.fill((42, 99, 161))
        frames = []
        for _ in range(3):
            frame = original.copy()
            crt.apply(frame)
            frames.append(pixels(frame))
        self.assertEqual(frames[0], frames[1])
        crt.clear_cache()
        frame = original.copy()
        crt.apply(frame)
        self.assertEqual(frames[0], pixels(frame))

    def test_forward_inverse_mapping_at_different_aspect_ratios(self):
        rng = random.Random(42)
        for enabled in (True, False):
            crt = CRTFilter(enabled=enabled, curvature_x=0.25, curvature_y=0.4)
            for size in ((320, 200), (240, 400), (1, 1)):
                for _ in range(20):
                    point = (rng.random() * size[0], rng.random() * size[1])
                    actual = crt.source_point(crt.display_point(point, size), size)
                    self.assertLess(math.dist(actual, point), 1e-9)

    def test_mouse_mapping_agrees_with_rendered_marker(self):
        for output_size in ((800, 500), (800, 600), (420, 740)):
            for enabled in (True, False):
                with self.subTest(size=output_size, enabled=enabled):
                    crt = CRTFilter(
                        enabled=enabled, scanlines=False, phosphor=False, vignette=False
                    )
                    source = pygame.Surface((320, 200))
                    point = (284, 32)
                    pygame.draw.rect(source, (255, 0, 0), (point[0] - 4, point[1] - 4, 8, 8))
                    target = pygame.Surface(output_size)
                    view = crt.render(source, target)
                    boxes = pygame.mask.from_threshold(
                        target, (255, 0, 0), (30, 30, 30, 255)
                    ).get_bounding_rects()
                    self.assertTrue(boxes)
                    shown = boxes[0].center
                    mapped = crt.map_to_source(shown, source.get_size(), view)
                    self.assertIsNotNone(mapped)
                    self.assertLess(math.dist(mapped, point), 2.5)

    def test_mouse_rejects_letterbox_and_curved_corners(self):
        crt = CRTFilter()
        view = crt.viewport((320, 200), pygame.Rect(0, 0, 800, 800))
        self.assertIsNone(crt.map_to_source((0, 0), (320, 200), view))
        self.assertIsNone(crt.map_to_source((view.x + 1, view.y + 1), (320, 200), view))
        self.assertEqual(crt.map_to_source(view.center, (320, 200), view), (160, 100))

    def test_round_bezel_corner_is_inert_even_without_curvature(self):
        crt = plain()
        crt.configure(bezel=True)
        view = pygame.Rect(10, 10, 600, 400)
        self.assertIsNone(crt.map_to_source((11, 11), (600, 400), view))
        self.assertEqual(crt.map_to_source((11, 11), (600, 400), view, bezel=False), (1, 1))

    def test_render_preserves_source_and_pixels_outside_destination(self):
        source = pygame.Surface((128, 80))
        source.fill((80, 160, 240))
        before = pixels(source)
        target = pygame.Surface((400, 300))
        target.fill((255, 0, 255))
        rect = pygame.Rect(30, 25, 330, 240)
        viewport = CRTFilter().render(source, target, rect)
        self.assertTrue(rect.contains(viewport))
        self.assertEqual(pixels(source), before)
        self.assertEqual(target.get_at((0, 0))[:3], (255, 0, 255))
        self.assertEqual(target.get_at((399, 299))[:3], (255, 0, 255))

    def test_invalid_destination_is_rejected(self):
        source, target = pygame.Surface((20, 10)), pygame.Surface((40, 30))
        with self.assertRaisesRegex(ValueError, "fully inside"):
            CRTFilter().render(source, target, pygame.Rect(-1, 0, 20, 10))

    def test_bezel_toggle_and_aspect_fit(self):
        crt = CRTFilter()
        source = (400, 600)
        outer = pygame.Rect(0, 0, 800, 600)
        small = crt.viewport(source, outer)
        crt.configure(bezel=False)
        large = crt.viewport(source, outer)
        self.assertGreater(large.height, small.height)
        self.assertEqual(large.size, (400, 600))
        crt.configure(bezel=True)
        crt.enabled = False
        self.assertEqual(crt.viewport(source, outer), large)


if __name__ == "__main__":
    unittest.main()
