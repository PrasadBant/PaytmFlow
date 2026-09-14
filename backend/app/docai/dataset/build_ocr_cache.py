"""Runs real OCR once over every generated document (all splits) and
caches the result to `<split>/ocr_cache.jsonl`, keyed by sample_id.

This is not a shortcut around measuring OCR - `ocr.py`'s Tesseract call is
genuinely executed here, once per sample, and the resulting text/confidence
is exactly what training and evaluation consume downstream. Caching only
avoids re-running the (comparatively slow) OCR pass every time the
classifier or extractor is retrained/evaluated during development.

Run: `uv run python -m app.docai.dataset.build_ocr_cache`
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.docai.dataset.generate import DATASET_ROOT as LENDING_DATASET_ROOT
from app.docai.ocr import extract_text


def build_cache_for_split(split: str, dataset_root: Path = LENDING_DATASET_ROOT) -> dict:
    split_dir = dataset_root / split
    labels_path = split_dir / "labels.jsonl"
    if not labels_path.exists():
        return {"split": split, "count": 0}

    records = []
    t0 = time.time()
    with labels_path.open(encoding="utf-8") as f:
        for line in f:
            label = json.loads(line)
            img_path = dataset_root / label["image_path"]
            content = img_path.read_bytes()
            result = extract_text(content, "image/jpeg")
            records.append(
                {
                    "sample_id": label["sample_id"],
                    "text": result.text,
                    "mean_word_confidence": result.mean_word_confidence,
                    "engine": result.engine,
                    "word_count": result.word_count,
                    "lines": [
                        {"text": ln.text, "top": ln.top, "bottom": ln.bottom} for ln in result.lines
                    ],
                }
            )
    elapsed = time.time() - t0

    out_path = split_dir / "ocr_cache.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    return {"split": split, "count": len(records), "seconds": round(elapsed, 2)}


if __name__ == "__main__":
    for split in ("train", "val", "test", "unseen_template"):
        stats = build_cache_for_split(split)
        print(stats)
