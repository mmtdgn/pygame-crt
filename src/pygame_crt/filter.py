"""Cached CPU rendering; no window creation, global state, assets, or OpenGL.

The two-pass glass warp and restrained phosphor treatment were extracted from
OVERDRILL's software renderer and generalized for independent Pygame projects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from numbers import Real

import pygame

Size = tuple[int, int]
Point = tuple[float, float]


def _size(size: Size) -> Size:
    if len(size) != 2 or any(type(n) is not int or n <= 0 for n in size):
        raise ValueError("size must contain two positive integers")
    return size[0], size[1]


@dataclass(frozen=True)
class CRTConfig:
    """Immutable settings. Use CRTFilter.configure() to change them at runtime."""

    curvature_x: float = 0.055
    curvature_y: float = 0.075
    scanlines: bool = True
    scanline_alpha: int = 20
    scanline_spacing: int = 0  # 0: adapt to output height, minimum 3 pixels
    phosphor: bool = True
    phosphor_alpha: int = 9
    vignette: bool = True
    vignette_alpha: int = 30
    bloom: bool = False
    bloom_threshold: int = 100
    bloom_strength: float = 0.22
    bezel: bool = True  # Used by render(); apply() never reserves a border.
    bezel_ratio: float = 1 / 60  # Margin as a fraction of the shorter output side
    background: tuple[int, int, int] = (2, 5, 8)

    def __post_init__(self) -> None:
        for name in ("scanlines", "phosphor", "vignette", "bloom", "bezel"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a bool")
        for name in ("scanline_alpha", "phosphor_alpha", "vignette_alpha", "bloom_threshold"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 255:
                raise ValueError(f"{name} must be an integer in [0, 255]")
        for name, maximum in (
            ("curvature_x", 0.5),
            ("curvature_y", 0.5),
            ("bloom_strength", 1.0),
            ("bezel_ratio", 0.2),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(value)
                or not 0 <= value <= maximum
            ):
                raise ValueError(f"{name} must be a finite number in [0, {maximum}]")
        if type(self.scanline_spacing) is not int or self.scanline_spacing < 0:
            raise ValueError("scanline_spacing must be a non-negative integer")
        if (
            not isinstance(self.background, tuple)
            or len(self.background) != 3
            or any(type(n) is not int or not 0 <= n <= 255 for n in self.background)
        ):
            raise ValueError("background must be an (R, G, B) tuple in [0, 255]")


class CRTFilter:
    """Reusable CRT effect. Create once; redraw the source before each call.

    apply(surface) modifies a completed frame in place.
    render(source, target) scales, filters, and frames without changing source.
    Coordinate helpers use the same continuous warp as the renderer (the actual
    pixels are rounded to integer strips, so allow a small rasterization error).
    """

    def __init__(self, config: CRTConfig | None = None, *, enabled: bool = True, **options):
        self._config = replace(config or CRTConfig(), **options)
        self.enabled = enabled
        self.clear_cache()

    @property
    def config(self) -> CRTConfig:
        return self._config

    def configure(self, **options) -> None:
        """Validate settings atomically, then invalidate size-dependent caches."""
        config = replace(self._config, **options)
        if config != self._config:
            self._config = config
            self.clear_cache()

    def clear_cache(self) -> None:
        """Release work surfaces. They are rebuilt lazily on the next frame."""
        self._size: Size | None = None
        self._work = self._horizontal = self._curved = None
        self._overlay = self._shade = self._frame = None
        self._bloom_surfaces = None
        self._rows: list = []
        self._columns: list = []
        self._render_buffer = None
        self._render_key = self._frame_key = None

    @staticmethod
    def _check_surface(surface: pygame.Surface) -> None:
        _size(surface.get_size())
        if surface.get_bitsize() not in (24, 32):
            raise ValueError("CRTFilter requires a 24-bit or 32-bit software Surface")
        if surface.get_locked():
            raise ValueError("Unlock the Surface before applying CRTFilter")

    @staticmethod
    def _runs(length: int, extent: int, strength: float):
        start, previous = 0, None
        for index in range(length):
            value = max(
                1, round(extent / (1 + strength * ((index + 0.5 - length / 2) / (length / 2)) ** 2))
            )
            if previous is not None and value != previous:
                yield start, index - start, previous
                start = index
            previous = value
        yield start, length - start, previous

    def _prepare(self, size: Size) -> None:
        if self._size == size:
            return
        self._size = size
        w, h = size
        c = self.config
        self._work = pygame.Surface(size, depth=32)
        self._rows, self._columns = [], []
        self._horizontal = self._curved = None
        if c.curvature_x or c.curvature_y:
            self._horizontal = pygame.Surface(size, depth=32)
            self._curved = pygame.Surface(size, depth=32)
            for y, height, width in self._runs(h, w, c.curvature_x):
                source = self._work.subsurface((0, y, w, height))
                dest = self._horizontal.subsurface(((w - width) // 2, y, width, height))
                self._rows.append((source, dest))
            for x, width, height in self._runs(w, h, c.curvature_y):
                source = self._horizontal.subsurface((x, 0, width, h))
                dest = self._curved.subsurface((x, (h - height) // 2, width, height))
                self._columns.append((source, dest))
        self._overlay = None
        if c.scanlines or c.phosphor:
            self._overlay = pygame.Surface(size, pygame.SRCALPHA, 32)
            pitch = c.scanline_spacing or max(3, round(h / 240))
            if c.phosphor:
                for x in range(0, w, pitch):
                    pygame.draw.line(
                        self._overlay, (30, 70, 110, c.phosphor_alpha), (x, 0), (x, h - 1)
                    )
            if c.scanlines:
                for y in range(0, h, pitch):
                    pygame.draw.line(self._overlay, (0, 0, 0, c.scanline_alpha), (0, y), (w - 1, y))
        self._shade = None
        if c.vignette:
            sw, sh = min(96, w), min(96, h)
            shade = pygame.Surface((sw, sh), pygame.SRCALPHA, 32)
            for y in range(sh):
                for x in range(sw):
                    nx = 2 * x / max(1, sw - 1) - 1 if sw > 1 else 0
                    ny = 2 * y / max(1, sh - 1) - 1 if sh > 1 else 0
                    alpha = round(c.vignette_alpha * min(1, (nx * nx + ny * ny) / 2) ** 1.6)
                    shade.set_at((x, y), (3, 7, 14, alpha))
            self._shade = pygame.transform.smoothscale(shade, size)
        self._bloom_surfaces = None
        if c.bloom:
            small = max(1, w // 4), max(1, h // 4)
            tiny = max(1, small[0] // 2), max(1, small[1] // 2)
            self._bloom_surfaces = tuple(
                pygame.Surface(s, depth=32) for s in (small, tiny, small, size)
            )

    def apply(self, surface: pygame.Surface) -> pygame.Surface:
        """Filter in place and return the same surface; disabled is an exact no-op.

        Input is a complete RGB frame. Alpha surfaces are composited onto
        config.background; transparency is not preserved. Display flipping and
        event handling remain the caller's responsibility.
        """
        if not self.enabled:
            return surface
        self._check_surface(surface)
        self._prepare(surface.get_size())
        work, c = self._work, self.config
        work.fill(c.background)
        work.blit(surface, (0, 0))
        if self._bloom_surfaces is not None:
            small, tiny, soft, blurred = self._bloom_surfaces
            pygame.transform.scale(work, small.get_size(), small)
            small.fill((c.bloom_threshold,) * 3, special_flags=pygame.BLEND_RGB_SUB)
            small.fill((round(c.bloom_strength * 255),) * 3, special_flags=pygame.BLEND_RGB_MULT)
            pygame.transform.scale(small, tiny.get_size(), tiny)
            pygame.transform.smoothscale(tiny, soft.get_size(), soft)
            pygame.transform.smoothscale(soft, work.get_size(), blurred)
            work.blit(blurred, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        if self._overlay is not None:
            work.blit(self._overlay, (0, 0))
        if self._shade is not None:
            work.blit(self._shade, (0, 0))
        output = work
        if self._horizontal is not None:
            self._horizontal.fill(c.background)
            self._curved.fill(c.background)
            for source, dest in self._rows:
                pygame.transform.smoothscale(source, dest.get_size(), dest)
            for source, dest in self._columns:
                pygame.transform.smoothscale(source, dest.get_size(), dest)
            output = self._curved
        surface.blit(output, (0, 0))
        # The result is a completed opaque frame, including for alpha/colorkey
        # inputs. Do not apply their original transparency a second time later.
        surface.set_alpha(None)
        surface.set_colorkey(None)
        return surface

    def display_point(self, point: Point, size: Size) -> Point:
        """Map a local unwarped pixel coordinate onto the curved picture."""
        w, h = _size(size)
        x, y = point
        if self.enabled:
            x = (x - w / 2) / (1 + self.config.curvature_x * ((y - h / 2) / (h / 2)) ** 2) + w / 2
            y = (y - h / 2) / (1 + self.config.curvature_y * ((x - w / 2) / (w / 2)) ** 2) + h / 2
        return x, y

    def source_point(self, point: Point, size: Size) -> Point:
        """Invert display_point(); does not clamp or reject outside coordinates."""
        w, h = _size(size)
        x, y = point
        if self.enabled:
            y = (y - h / 2) * (1 + self.config.curvature_y * ((x - w / 2) / (w / 2)) ** 2) + h / 2
            x = (x - w / 2) * (1 + self.config.curvature_x * ((y - h / 2) / (h / 2)) ** 2) + w / 2
        return x, y

    def viewport(self, source_size: Size, destination: pygame.Rect) -> pygame.Rect:
        """Aspect-fit source into destination; reserve bezel space when enabled."""
        sw, sh = _size(source_size)
        outer = pygame.Rect(destination)
        _size(outer.size)
        margin = 0
        if self.enabled and self.config.bezel:
            margin = min(
                round(min(outer.size) * self.config.bezel_ratio), (min(outer.size) - 1) // 2
            )
        available = outer.inflate(-margin * 2, -margin * 2)
        scale = min(available.width / sw, available.height / sh)
        view = pygame.Rect(0, 0, max(1, round(sw * scale)), max(1, round(sh * scale)))
        view.center = outer.center
        return view

    def _outline(self, size: Size) -> list[Point]:
        w, h = size
        radius = min(w, h) * 0.035
        corners = (
            (radius, radius, 180),
            (w - radius, radius, 270),
            (w - radius, h - radius, 0),
            (radius, h - radius, 90),
        )
        outline = []
        for i, (cx, cy, angle) in enumerate(corners):
            for step in range(13):
                a = math.radians(angle + 90 * step / 12)
                outline.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
            nx, ny, na = corners[(i + 1) % 4]
            a = math.radians(na)
            start, end = outline[-1], (nx + radius * math.cos(a), ny + radius * math.sin(a))
            for step in range(1, 33):
                t = step / 33
                outline.append(
                    (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)
                )
        return [self.display_point(p, size) for p in outline]

    def _draw_bezel(self, target: pygame.Surface, outer: pygame.Rect, view: pygame.Rect) -> None:
        local = view.move(-outer.x, -outer.y)
        key = (outer.size, tuple(local))
        if self._frame_key != key:
            frame = pygame.Surface(outer.size, pygame.SRCALPHA, 32)
            frame.fill((*self.config.background, 255))
            outline = self._outline(local.size)
            scale = min(local.size) / 720

            def contour(padding):
                sx, sy = 1 + padding * 2 / local.width, 1 + padding * 2 / local.height
                return [
                    (
                        round(local.centerx + (x - local.width / 2) * sx),
                        round(local.centery + (y - local.height / 2) * sy),
                    )
                    for x, y in outline
                ]

            for padding, color in (
                (8, (15, 20, 25)),
                (5, (64, 74, 79)),
                (4, (19, 27, 32)),
                (2, (7, 11, 15)),
            ):
                pygame.draw.polygon(frame, color, contour(max(1, round(padding * scale))))
            pygame.draw.polygon(frame, (0, 0, 0, 0), contour(0))
            self._frame, self._frame_key = frame, key
        target.blit(self._frame, outer.topleft)

    def render(
        self, source: pygame.Surface, target: pygame.Surface, rect: pygame.Rect | None = None
    ) -> pygame.Rect:
        """Draw an aspect-fitted frame with optional bezel; return the viewport.

        source is never modified unless it aliases target. rect is in target
        coordinates and must be fully inside it. Scaling uses nearest-neighbor;
        the glass warp uses smoothscale. Pixels outside rect are left alone.
        """
        self._check_surface(source)
        self._check_surface(target)
        outer = target.get_rect() if rect is None else pygame.Rect(rect)
        _size(outer.size)
        if not target.get_rect().contains(outer):
            raise ValueError("rect must be fully inside the target surface")
        view = self.viewport(source.get_size(), outer)
        key = (view.size, source.get_bitsize(), source.get_masks())
        if self._render_key != key:
            self._render_buffer = pygame.Surface(
                view.size, pygame.SRCALPHA if source.get_masks()[3] else 0, source
            )
            self._render_key = key
        pygame.transform.scale(source, view.size, self._render_buffer)
        # scale() with a destination does not transfer the source's alpha/key
        # settings. Restore them, including after apply() flattened this buffer.
        self._render_buffer.set_alpha(source.get_alpha())
        self._render_buffer.set_colorkey(source.get_colorkey())
        self.apply(self._render_buffer)
        target.fill(self.config.background, outer)
        target.blit(self._render_buffer, view.topleft)
        if self.enabled and self.config.bezel:
            self._draw_bezel(target, outer, view)
        return view

    def map_to_source(
        self, point: Point, source_size: Size, viewport: pygame.Rect, *, bezel: bool = True
    ) -> Point | None:
        """Map a mouse point through render()'s returned viewport into source pixels.

        Returns None for letterboxing, curved black corners, and the rounded
        bezel. Pass bezel=False when mapping a surface filtered by apply().
        """
        sw, sh = _size(source_size)
        view = pygame.Rect(viewport)
        _size(view.size)
        if not view.collidepoint(point):
            return None
        x, y = self.source_point((point[0] - view.x, point[1] - view.y), view.size)
        if not (0 <= x < view.width and 0 <= y < view.height):
            return None
        if bezel and self.enabled and self.config.bezel:
            radius = min(view.size) * 0.035
            dx = max(radius - x, x - (view.width - radius), 0)
            dy = max(radius - y, y - (view.height - radius), 0)
            if dx * dx + dy * dy > radius * radius:
                return None
        return x * sw / view.width, y * sh / view.height
