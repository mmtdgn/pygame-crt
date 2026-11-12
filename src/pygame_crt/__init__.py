"""CRT post-processing for complete, software-rendered Pygame frames."""

try:
    import pygame as _pygame  # noqa: F401
except ModuleNotFoundError as exc:
    if exc.name != "pygame":
        raise
    raise ModuleNotFoundError(
        "pygame-crt needs a backend. Install pygame-crt[ce] or pygame-crt[pygame] "
        "(choose one), or install pygame-ce / pygame separately."
    ) from exc

from .filter import CRTConfig, CRTFilter

__all__ = ["CRTConfig", "CRTFilter"]
__version__ = "0.1.0"
