import os
import tempfile
import unittest
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

from pygame_crt import CRTFilter
from pygame_crt.demo import SOURCE_SIZE, Scene, handle_event, main


class DemoTests(unittest.TestCase):
    def test_demo_runs_and_saves_visible_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            self.assertEqual(main(["--headless", "--frames", "3", "--screenshot", str(path)]), 0)
            frame = pygame.image.load(str(path))
            self.assertEqual(frame.get_size(), (960, 600))
            self.assertGreater(len(set(pygame.image.tobytes(frame, "RGB"))), 100)

    def test_demo_events_use_curved_click_mapping_and_toggle_effects(self):
        pygame.display.init()
        pygame.font.init()
        try:
            scene, crt = Scene(), CRTFilter()
            view = crt.viewport(SOURCE_SIZE, pygame.Rect(0, 0, 960, 600))
            point = (
                scene.button.centerx * view.width / SOURCE_SIZE[0],
                scene.button.centery * view.height / SOURCE_SIZE[1],
            )
            x, y = crt.display_point(point, view.size)
            click = pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=(round(view.x + x), round(view.y + y))
            )
            handle_event(click, scene, crt, view)
            self.assertEqual(scene.hits, 1)
            for key in (pygame.K_F2, pygame.K_F3, pygame.K_F4, pygame.K_RIGHTBRACKET):
                self.assertTrue(
                    handle_event(pygame.event.Event(pygame.KEYDOWN, key=key), scene, crt, view)
                )
            source, target = pygame.Surface(SOURCE_SIZE), pygame.Surface((600, 900))
            scene.draw(source, crt)
            view = crt.render(source, target)
            self.assertFalse(crt.config.scanlines)
            self.assertTrue(crt.config.bloom)
            self.assertFalse(crt.config.bezel)
            handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1), scene, crt, view)
            self.assertFalse(crt.enabled)
            self.assertFalse(handle_event(pygame.event.Event(pygame.QUIT), scene, crt, view))
        finally:
            pygame.quit()


if __name__ == "__main__":
    unittest.main()
