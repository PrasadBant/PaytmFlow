"""OCR engine benchmark: DocTR vs Tesseract, same frozen evaluation
documents (val/test/unseen_template), same extraction/normalization code
downstream - only the OCR text/line source differs.

Must run in the ISOLATED `.venv-ocr-bench` environment (DocTR/torch are
NOT added to the production `pyproject.toml` - this is a one-time
comparison, not a shipped dependency):

    uv run --python .venv-ocr-bench python -m app.docai.bench_ocr_doctr

(invoked directly as a script since app.docai.extraction has no heavy
deps and importable standalone; this file intentionally does not import
anything from app.docai.ocr to avoid a pytesseract import in the bench venv)
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


def run_doctr_ocr(model, image_path: Path) -> tuple[str, list[OcrLine], float, int]:
    from doctr.io import DocumentFile

    doc = DocumentFile.from_images(str(image_path))
    result = model(doc)
    page = result.pages[0]
    page_h, page_w = page.dimensions

    lines: list[OcrLine] = []
    words_all: list[str] = []
    confidences: list[float] = []
    for block in page.blocks:
        for line in block.lines:
            words = [w.value for w in line.words]
            confidences.extend(w.confidence for w in line.words)
            words_all.extend(words)
            # geometry is ((xmin,ymin),(xmax,ymax)) in RELATIVE (0-1)
            # coords - convert to pixel-ish coords comparable to
            # Tesseract's (top/bottom in pixels) so the SAME extraction
            # code (which only compares relative distances) works
            # unmodified.
            (_, ymin), (_, ymax) = line.geometry
            lines.append(
                OcrLine(text=" ".join(words), top=int(ymin * page_h), bottom=int(ymax * page_h))
            )

    text = "\n".join(ln.text for ln in lines)
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return text, lines, mean_conf, len(words_all)


def evaluate() -> dict:
    from doctr.models import ocr_predictor

    model = ocr_predictor(pretrained=True)

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
            text, lines, conf, word_count = run_doctr_ocr(model, rec["image_path"])
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

    out = {"engine": "doctr", "results": results}
    reports_dir = DATASET_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "ocr_bench_doctr.json").write_text(json.dumps(out, indent=2))
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
