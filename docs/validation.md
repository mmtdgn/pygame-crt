# Validation

This file records checks for version 0.1.0. CI results for the published commit
are available in the repository's Actions tab.

Local release checks were run on 2026-11-12 in isolated virtual environments for
pygame-ce 2.5.8 and Pygame 2.6.1 on Windows with Python 3.10.11. All 23 tests
passed with each backend. The tests cover
rendered mouse targets, resizing, portrait and landscape aspect ratios, tiny
frames, alpha flattening, bloom, input validation, demo controls, and packaging.

Run the checks from the README to reproduce validation. Performance measurements
are warm-cache CPU timings for the procedural demo, including scaling and the
bezel, excluding display flip. They are machine-specific, not FPS guarantees.

One local run using pygame-ce 2.5.8, default settings (bloom off), 30 measured
frames after warming caches, and a 640 x 400 source produced:

| Destination size | Median render time |
| --- | --- |
| 640 x 400 | 1.051 ms |
| 1280 x 720 | 3.491 ms |
| 1920 x 1080 | 9.008 ms |

The source is aspect-fitted into each destination; the filter processes the
inner viewport. These timings exclude drawing the scene and do not establish a
minimum hardware requirement or promise a particular game frame rate.
