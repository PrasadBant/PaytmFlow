"""OCR engine benchmark: PaddleOCR vs Tesseract/DocTR, same frozen
evaluation documents. See bench_ocr_doctr.py for the shared methodology
notes. Run in the isolated `.venv-ocr-bench` environment:

    .venv-ocr-bench/Scripts/python.exe app/docai/bench_ocr_paddleocr.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.docai.dataset.generate import DATASET_ROOT  # noqa: E402
from app.docai.extraction import extract_fields_for_doc_type  # noqa: E402
from app.docai.ocr import OcrLine  # noqa: E402


def _load_split(split: str) -> list[dict]:
    split_dir = DATASET_ROOT / split
    labels = {}
    with (split_dir / "labels.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            labels[rec["sample_id"]] = rec
    return [
        {**rec, "image_path": split_dir.parent / rec["image_path"]}
        for rec in labels.values()
        if rec["doc_type"] not in ("UNREADABLE", "OTHER")
    ]


def run_paddleocr(engine, image_path: Path) -> tuple[str, list[OcrLine], float, int]:
    result = engine.predict(str(image_path))
    page = result[0]

    texts = page.get("rec_texts") or []
    scores = page.get("rec_scores") or []
    polys = page.get("rec_polys") or page.get("dt_polys") or []

    lines: list[OcrLine] = []
    for text, poly in zip(texts, polys, strict=False):
        ys = [pt[1] for pt in poly]
        lines.append(OcrLine(text=text, top=int(min(ys)), bottom=int(max(ys))))

    full_text = "\n".join(texts)
    mean_conf = sum(scores) / len(scores) if scores else 0.0
    word_count = sum(len(t.split()) for t in texts)
    return full_text, lines, mean_conf, word_count


def evaluate() -> dict:
    from paddleocr import PaddleOCR

    engine = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        lang="en",
        # Without this, PaddlePaddle 3.3.1's oneDNN CPU inference path
        # throws a real, reproducible NotImplementedError
        # ("ConvertPirAttribute2RuntimeAttribute not support...") on this
        # machine - a genuine environment/version incompatibility, not a
        # data issue. Disabling oneDNN acceleration (falls back to plain
        # CPU inference) works around it; documented as measured, not
        # guessed.
        enable_mkldnn=False,
    )

    splits = {s: _load_split(s) for s in ("val", "test", "unseen_template")}
    results: dict[str, dict] = {}

    for split_name, records in splits.items():
        n = 0
        conf_sum = 0.0
        latency_sum = 0.0
        field_n = 0
        field_match = 0
        for rec in records:
            t0 = time.time()
            text, lines, conf, word_count = run_paddleocr(engine, rec["image_path"])
            latency_sum += time.time() - t0
            n += 1
            conf_sum += conf

            extracted = {
                f.key: f for f in extract_fields_for_doc_type(text, rec["doc_type"], lines=lines)
            }
            for field_key, gt_value in rec["fields"].items():
                if field_key not in ("monthly_income", "employer_name"):
                    continue
                field_n += 1
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
                    field_match += 1

        results[split_name] = {
            "n_documents": n,
            "mean_ocr_confidence": round(conf_sum / n, 4) if n else None,
            "mean_latency_seconds": round(latency_sum / n, 4) if n else None,
            "field_n": field_n,
            "field_exact_match_accuracy": round(field_match / field_n, 4) if field_n else None,
        }

    out = {"engine": "paddleocr", "results": results}
    reports_dir = DATASET_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "ocr_bench_paddleocr.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    out = evaluate()
    for split, res in out["results"].items():
        print(
            f"{split:16s} n={res['n_documents']:3d}  "
            f"mean_ocr_confidence={res['mean_ocr_confidence']}  "
            f"mean_latency_s={res['mean_latency_seconds']}  "
            f"field_exact_match_accuracy={res['field_exact_match_accuracy']}"
        )
