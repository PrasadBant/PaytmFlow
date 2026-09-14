"""Real image preprocessing before OCR: deskew correction.

Why not Tesseract's own OSD (`pytesseract.image_to_osd`): tested directly
against this pipeline's own rotated samples and confirmed it only detects
GROSS orientation in multiples of 90 degrees ("Rotate: 0/90/180/270") -
for a real photographed/scanned document's few-degree skew (this
project's synthetic data uses up to ±3.5°, and a real phone photo is
routinely in that range too), OSD reports "Rotate: 0" and is useless for
correction. This is a measured fact about this environment's Tesseract
5.4.0, not an assumption.

Instead, tried here: a standard projection-profile deskew. Correctly-
aligned text rows produce a horizontal pixel-density profile with sharp
peaks (between-row whitespace) and troughs (text rows); a skewed image
blurs those peaks together. Trying a small range of candidate rotation
angles and picking the one that maximizes profile peakiness (variance of
row-sums) is a well-established, generalizable technique - not tuned to
any one document template.

MEASURED RESULT - NOT WIRED INTO THE PIPELINE: tested against every
sample in the frozen val/test/unseen_template splits with rotation
>= 2 degrees (53 documents), both rotation directions, and with the
zero-degradation control. In every direction tried, it made OCR mean
word confidence and/or word count WORSE, not better (e.g. one sample:
baseline confidence 0.8519 -> 0.8397 (matching the estimator's own
chosen correction) / 0.8114 (opposite direction); several samples lost
the majority of their recognized words entirely, e.g. 66 words -> 25,
40 -> 4). Root cause not fully isolated (plausibly: the downscaled
thumbnail used for angle search is not sensitive enough for this
pipeline's small-glyph documents; a second bicubic resampling pass adds
its own blur that costs more than the mild original skew did), but the
practical conclusion is unambiguous - per this project's own rule ("do
not simply make preprocessing more aggressive if it damages clean
documents" / "if [a change] performs worse, do not force it into
production"), this function is kept in the repo as a DOCUMENTED,
MEASURED, REJECTED experiment, and is intentionally not called from
`ocr.py`. See docs/docai_report.md for the full before/after table.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

_CANDIDATE_ANGLES = [round(a * 0.5, 1) for a in range(-10, 11)]  # -5.0 .. +5.0 in 0.5 steps


def _row_profile_variance(gray_arr: np.ndarray) -> float:
    """Higher variance = sharper peaks/troughs = better row alignment."""
    row_sums = gray_arr.sum(axis=1).astype(np.float64)
    return float(row_sums.var())


def estimate_skew_angle(pil_image: Image.Image) -> float:
    """Returns the estimated skew angle (degrees) that best aligns text
    rows horizontally, searched over `_CANDIDATE_ANGLES`. Returns 0.0 if
    the image is too small/blank to measure meaningfully."""
    gray = ImageOps.grayscale(pil_image)
    # Downscale for speed - skew estimation doesn't need full resolution,
    # and this keeps the per-document cost of trying 21 angles low.
    gray.thumbnail((600, 800))
    arr = 255 - np.asarray(gray, dtype=np.float64)  # invert: text = high value

    if arr.size == 0 or arr.max() == 0:
        return 0.0

    best_angle = 0.0
    best_variance = -1.0
    for angle in _CANDIDATE_ANGLES:
        rotated = Image.fromarray(arr.astype(np.uint8)).rotate(
            angle, expand=False, fillcolor=0, resample=Image.Resampling.BILINEAR
        )
        variance = _row_profile_variance(np.asarray(rotated, dtype=np.float64))
        if variance > best_variance:
            best_variance = variance
            best_angle = angle
    return best_angle


def deskew(pil_image: Image.Image) -> tuple[Image.Image, float]:
    """Returns (corrected_image, applied_angle_degrees). Rotates the full-
    resolution image by the NEGATIVE of the estimated skew (to undo it),
    filling exposed corners with white (matches this pipeline's own scan
    background, not an arbitrary color)."""
    angle = estimate_skew_angle(pil_image)
    if angle == 0.0:
        return pil_image, 0.0
    corrected = pil_image.convert("RGB").rotate(
        -angle, expand=False, fillcolor=(255, 255, 255), resample=Image.Resampling.BICUBIC
    )
    return corrected, angle
