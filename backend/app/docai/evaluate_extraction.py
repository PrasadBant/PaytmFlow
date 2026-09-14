"""Measures real field-extraction accuracy against ground truth, split by
split and by field - not a single invented accuracy number (mission
Phase 18).

Run: `uv run python -m app.docai.evaluate_extraction`
"""

from __future__ import annotations

import json
from pathlib import Path

from app.docai.dataset.generate import DATASET_ROOT as LENDING_DATASET_ROOT
from app.docai.extraction import extract_fields_for_doc_type
from app.docai.normalize import normalize_date
from app.docai.ocr import OcrLine

# Lending's real manifest target fields (monthly_income, employer_name).
# Insurance and future packs pass their own `scored_fields` explicitly -
# this default preserves the exact original Lending CLI behavior.
LENDING_SCORED_FIELDS = ("monthly_income", "employer_name")

# Fields compared by substring-containment (free text, e.g. names) rather
# than exact equality (money, exact-value fields).
_FUZZY_FIELDS = {"employer_name", "name"}

# Fields where BOTH sides must be run through the same normalizer before
# comparing - the extractor's `value` is always normalized (ISO date), but
# ground truth in labels.jsonl is stored in the generator's own raw
# rendering format (DD/MM/YYYY); comparing normalized-vs-raw would
# understate a genuinely correct extraction as a "failure" purely from a
# format mismatch, not a real error - caught by tracing an early Insurance
# run where every date "failed" despite the extractor visibly returning
# the right calendar date in ISO form.
_DATE_FIELDS = {"document_date"}

# Same "normalize both sides before comparing" principle as _DATE_FIELDS
# above, now needed for `identifier`: the extractor always returns a
# stripped, uppercased value (no embedded spaces - see
# extraction.py::extract_identifier), but ground truth for a
# space-grouped real-world format (Aadhaar's "1234 5678 9012") is stored
# in that same realistic printed format, not pre-stripped - comparing
# stripped-vs-spaced understated a genuinely correct extraction as a
# "failure" purely from formatting, not a real error (caught tracing an
# Account Opening run where every Aadhaar extraction was byte-for-byte
# the right 12 digits yet still counted as a mismatch).
_IDENTIFIER_FIELDS = {"identifier"}


def _load_split(split: str, dataset_root: Path) -> list[dict]:
    split_dir = dataset_root / split
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
        if sid in ocr and label["doc_type"] not in ("UNREADABLE", "OTHER"):
            ocr_lines = [
                OcrLine(text=ln["text"], top=ln["top"], bottom=ln["bottom"])
                for ln in ocr[sid].get("lines", [])
            ]
            merged.append({**label, "ocr_text": ocr[sid]["text"], "ocr_lines": ocr_lines})
    return merged


def evaluate_split(split: str, dataset_root: Path, scored_fields: tuple[str, ...]) -> dict:
    records = _load_split(split, dataset_root)
    field_stats: dict[str, dict] = {}
    error_examples: list[dict] = []

    for rec in records:
        doc_type = rec["doc_type"]
        gt = rec["fields"]
        extracted = {
            f.key: f
            for f in extract_fields_for_doc_type(
                rec["ocr_text"], doc_type, lines=rec.get("ocr_lines")
            )
        }

        for field_key, gt_value in gt.items():
            if field_key not in scored_fields:
                continue  # scored fields = the manifest's real target fields only
            if field_key in _DATE_FIELDS:
                gt_value = normalize_date(str(gt_value)) or gt_value
            elif field_key in _IDENTIFIER_FIELDS:
                gt_value = str(gt_value).replace(" ", "").upper()
            stats = field_stats.setdefault(
                field_key, {"n": 0, "exact_match": 0, "extracted_not_null": 0, "missing_gt": 0}
            )
            stats["n"] += 1
            ext_field = extracted.get(field_key)
            predicted_value = ext_field.value if ext_field else None

            if predicted_value is not None:
                stats["extracted_not_null"] += 1

            is_match = False
            if field_key in _FUZZY_FIELDS:
                is_match = predicted_value is not None and (
                    str(gt_value).strip().lower() in str(predicted_value).strip().lower()
                    or str(predicted_value).strip().lower() in str(gt_value).strip().lower()
                )
            else:
                is_match = predicted_value == gt_value

            if is_match:
                stats["exact_match"] += 1
            else:
                error_examples.append(
                    {
                        "split": split,
                        "sample_id": rec["sample_id"],
                        "doc_type": doc_type,
                        "template_id": rec["template_id"],
                        "field": field_key,
                        "expected": gt_value,
                        "predicted": predicted_value,
                        "raw_value": ext_field.raw_value if ext_field else None,
                        "validated": ext_field.validated if ext_field else None,
                        "note": ext_field.validation_note if ext_field else "field not extracted",
                    }
                )

    summary = {}
    for field_key, stats in field_stats.items():
        n = stats["n"] or 1
        summary[field_key] = {
            "n": stats["n"],
            "exact_match_accuracy": round(stats["exact_match"] / n, 4),
            "extraction_coverage": round(stats["extracted_not_null"] / n, 4),
        }
    return {
        "split": split,
        "n_documents": len(records),
        "field_metrics": summary,
        "errors": error_examples,
    }


def run(
    dataset_root: Path = LENDING_DATASET_ROOT,
    scored_fields: tuple[str, ...] = LENDING_SCORED_FIELDS,
) -> dict:
    all_results = {
        split: evaluate_split(split, dataset_root, scored_fields)
        for split in ("val", "test", "unseen_template")
    }
    reports_dir = dataset_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "extraction_metrics.json").write_text(
        json.dumps(all_results, indent=2, default=str)
    )
    return all_results


if __name__ == "__main__":
    results = run()
    for split, res in results.items():
        print(f"\n=== {split} (n_documents={res['n_documents']}) ===")
        for field_key, m in res["field_metrics"].items():
            print(
                f"  {field_key:16s} n={m['n']:3d}  "
                f"exact_match_accuracy={m['exact_match_accuracy']:.4f}  "
                f"extraction_coverage={m['extraction_coverage']:.4f}"
            )
        print(f"  {len(res['errors'])} field-level error(s)")
