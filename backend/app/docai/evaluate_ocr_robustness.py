"""Breaks OCR + extraction performance down by document-quality tier
(clean / blurred / rotated / noisy / heavily JPEG-compressed), using the
degradation metadata already recorded per-sample by
`dataset/generate.py` - no new dataset needed, this is a re-slice of the
existing frozen val/test/unseen_template splits.

"Clean" here means the LEAST-degraded tier this dataset actually
generates (small rotation only, no blur/noise, high JPEG quality) - the
generator always applies at least a small random rotation to every
sample (mission Phase 5's "handle rotation" requirement), so there is no
zero-degradation control image; this is disclosed rather than implying a
perfectly clean baseline was tested.

Run: `uv run python -m app.docai.evaluate_ocr_robustness`
"""

from __future__ import annotations

import json
from pathlib import Path

from app.docai.dataset.generate import DATASET_ROOT
from app.docai.extraction import extract_fields_for_doc_type
from app.docai.ocr import OcrLine


def _tier_for(deg: dict) -> str:
    if not deg or deg.get("synthetic") == "blank_or_noise":
        return "unreadable_control"
    blur = deg.get("blur_radius", 0)
    noise = deg.get("noise_sigma", 0)
    quality = deg.get("jpeg_quality", 100)
    rotation = abs(deg.get("rotation_deg", 0))
    if blur:
        return "blurred"
    if noise:
        return "noisy"
    if quality <= 60:
        return "heavy_jpeg_compression"
    if rotation > 2.5:
        return "rotated"
    return "clean"


def _load_split(split: str) -> list[dict]:
    split_dir = DATASET_ROOT / split
    labels = {}
    with (split_dir / "labels.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            labels[rec["sample_id"]] = rec
    ocr = {}
    with (split_dir / "ocr_cache.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            ocr[rec["sample_id"]] = rec
    merged = []
    for sid, label in labels.items():
        if sid not in ocr or label["doc_type"] in ("UNREADABLE", "OTHER"):
            continue
        merged.append({**label, **ocr[sid]})
    return merged


def evaluate() -> dict:
    all_records = []
    for split in ("val", "test", "unseen_template"):
        all_records.extend(_load_split(split))

    by_tier: dict[str, dict] = {}
    for rec in all_records:
        tier = _tier_for(rec.get("degradation", {}))
        bucket = by_tier.setdefault(
            tier,
            {
                "n_documents": 0,
                "ocr_confidence_sum": 0.0,
                "ocr_word_count_sum": 0,
                "field_n": 0,
                "field_exact_match": 0,
            },
        )
        bucket["n_documents"] += 1
        bucket["ocr_confidence_sum"] += rec.get("mean_word_confidence", 0.0)
        bucket["ocr_word_count_sum"] += rec.get("word_count", 0)

        lines = [
            OcrLine(text=ln["text"], top=ln["top"], bottom=ln["bottom"])
            for ln in rec.get("lines", [])
        ]
        extracted = {
            f.key: f for f in extract_fields_for_doc_type(rec["text"], rec["doc_type"], lines=lines)
        }
        for field_key, gt_value in rec["fields"].items():
            if field_key not in ("monthly_income", "employer_name"):
                continue
            bucket["field_n"] += 1
            ext = extracted.get(field_key)
            predicted = ext.value if ext else None
            is_match = False
            if field_key == "monthly_income":
                is_match = predicted == gt_value
            elif predicted:
                is_match = (
                    str(gt_value).lower() in str(predicted).lower()
                    or str(predicted).lower() in str(gt_value).lower()
                )
            if is_match:
                bucket["field_exact_match"] += 1

    summary = {}
    for tier, b in sorted(by_tier.items()):
        n = b["n_documents"]
        summary[tier] = {
            "n_documents": n,
            "mean_ocr_confidence": round(b["ocr_confidence_sum"] / n, 4) if n else None,
            "mean_ocr_word_count": round(b["ocr_word_count_sum"] / n, 2) if n else None,
            "field_exact_match_accuracy": (
                round(b["field_exact_match"] / b["field_n"], 4) if b["field_n"] else None
            ),
            "field_n": b["field_n"],
        }

    reports_dir = DATASET_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    out_path: Path = reports_dir / "ocr_robustness_by_tier.json"
    out_path.write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    summary = evaluate()
    for tier, s in summary.items():
        print(
            f"{tier:24s} n={s['n_documents']:3d}  "
            f"mean_ocr_confidence={s['mean_ocr_confidence']}  "
            f"field_exact_match_accuracy={s['field_exact_match_accuracy']}  "
            f"(n_fields={s['field_n']})"
        )
