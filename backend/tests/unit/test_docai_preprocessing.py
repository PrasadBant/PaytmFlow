"""Tests for app/docai/preprocessing.py - a DOCUMENTED, MEASURED, REJECTED
deskew experiment (see the module docstring for the negative result).
These tests only verify the code runs correctly and returns sane types;
they do not assert it improves anything, because it doesn't and is not
wired into the pipeline.
"""

from PIL import Image

from app.docai.preprocessing import deskew, estimate_skew_angle


def _blank_image() -> Image.Image:
    return Image.new("RGB", (400, 600), color=(255, 255, 255))


class TestEstimateSkewAngle:
    def test_returns_zero_for_blank_image(self):
        assert estimate_skew_angle(_blank_image()) == 0.0

    def test_returns_a_float_within_candidate_range(self):
        angle = estimate_skew_angle(_blank_image())
        assert -5.0 <= angle <= 5.0


class TestDeskew:
    def test_zero_angle_returns_same_image_object(self):
        img = _blank_image()
        corrected, angle = deskew(img)
        assert angle == 0.0
        assert corrected is img

    def test_returns_correct_types(self):
        img = _blank_image()
        corrected, angle = deskew(img)
        assert isinstance(corrected, Image.Image)
        assert isinstance(angle, float)
