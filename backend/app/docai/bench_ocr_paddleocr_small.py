"""SMALL, reliable PaddleOCR benchmark - 8 representative Lending
documents, NOT the full 111-document frozen dataset (deliberately: the
previous full-dataset attempt appeared to hang for ~58 minutes while
running concurrently with two other CPU-heavy jobs, and had zero
per-document progress output to tell "still working" apart from "stuck" -
both problems are fixed here before attempting anything larger).

Run ALONE (no concurrent pytest/training jobs), in the isolated
`.venv-ocr-bench` environment:

    .venv-ocr-bench/Scripts/python.exe app/docai/bench_ocr_paddleocr_small.py

For a true apples-to-apples comparison, this script also re-runs
Tesseract and DocTR against the SAME 8 documents (not the full-dataset
numbers from earlier reports, which cover a different, larger sample) -
"comparable" per the request means same input set, not just same task.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.docai.dataset.generate import DATASET_ROOT  # noqa: E402
from app.docai.extraction import extract_fields_for_doc_type  # noqa: E402
from app.docai.ocr import OcrLine  # noqa: E402

# 8 documents, 2 per doc_type, deliberately spanning an easy (near-clean)
# and a hard (blurred/noisy/heavily-compressed/rotated) degradation
# profile each - chosen from the val split's real labels.jsonl, not
# cherry-picked for a favorable result (the exact degradation values are
# printed per-document below, from the dataset's own recorded metadata).
SAMPLE_IDS = [
    "SALARY_SLIP_salary_table_0031",  # near-clean
    "SALARY_SLIP_salary_table_0032",  # blurred + noisy + heavy compression
    "BANK_STATEMENT_bank_hdfc_0091",  # blurred + noisy + heavy compression
    "BANK_STATEMENT_bank_hdfc_0093",  # rotated + noisy
    "OFFICE_ID_CARD_id_horizontal_0141",  # near-clean, mild rotation
    "OFFICE_ID_CARD_id_horizontal_0142",  # rotated + noisy + heavy compression
    "OFFER_LETTER_offer_formal_0185",  # near-clean, mild noise
    "OFFER_LETTER_offer_formal_0186",  # rotated + noisy + heavy compression
]

PER_DOCUMENT_TIMEOUT_SECONDS = 45.0


def _load_records() -> list[dict]:
    split_dir = DATASET_ROOT / "val"
    labels = {}
    with (split_dir / "labels.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            labels[rec["sample_id"]] = rec
    records = []
    for sid in SAMPLE_IDS:
        rec = labels[sid]
        records.append({**rec, "image_path": DATASET_ROOT / rec["image_path"]})
    return records


def _score_extraction(doc_type: str, text: str, lines: list[OcrLine], gt_fields: dict) -> dict:
    extracted = {f.key: f for f in extract_fields_for_doc_type(text, doc_type, lines=lines)}
    scored = {}
    for field_key, gt_value in gt_fields.items():
        if field_key not in ("monthly_income", "employer_name"):
            continue
        ext = extracted.get(field_key)
        predicted = ext.value if ext else None
        if field_key == "monthly_income":
            is_match = predicted == gt_value
        else:
            is_match = bool(predicted) and (
                str(gt_value).lower() in str(predicted).lower()
                or str(predicted).lower() in str(gt_value).lower()
            )
        scored[field_key] = {"expected": gt_value, "predicted": predicted, "match": is_match}
    return scored


def _run_paddleocr_one(engine, image_path: Path) -> tuple[str, list[OcrLine], float, int]:
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


def bench_paddleocr(records: list[dict]) -> dict:
    print(
        "[paddleocr] loading engine (enable_mkldnn=False, this is the known-required "
        "workaround for a real PaddlePaddle 3.3.1 CPU-inference NotImplementedError "
        "on this machine)...",
        flush=True,
    )
    from paddleocr import PaddleOCR

    t_load_start = time.time()
    try:
        engine = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang="en",
            enable_mkldnn=False,
        )
    except Exception as exc:
        print(f"[paddleocr] ENGINE LOAD FAILED: {exc!r}", flush=True)
        return {
            "engine": "paddleocr",
            "config": {"enable_mkldnn": False},
            "engine_load_failed": True,
            "engine_load_error": repr(exc),
            "per_document": [],
        }
    load_seconds = time.time() - t_load_start
    print(f"[paddleocr] engine loaded in {load_seconds:.1f}s", flush=True)

    per_document = []
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        for i, rec in enumerate(records, start=1):
            sid = rec["sample_id"]
            print(
                f"[paddleocr] ({i}/{len(records)}) {sid} "
                f"[{rec['doc_type']}, degradation={rec['degradation']}] starting...",
                flush=True,
            )
            entry = {
                "sample_id": sid,
                "doc_type": rec["doc_type"],
                "degradation": rec["degradation"],
                "success": False,
                "timed_out": False,
                "elapsed_seconds": None,
                "text_length": None,
                "error": None,
                "extraction": None,
            }
            t0 = time.time()
            future = executor.submit(_run_paddleocr_one, engine, rec["image_path"])
            try:
                text, lines, conf, word_count = future.result(timeout=PER_DOCUMENT_TIMEOUT_SECONDS)
                elapsed = time.time() - t0
                entry.update(
                    success=True,
                    elapsed_seconds=round(elapsed, 3),
                    text_length=len(text),
                    ocr_confidence=round(conf, 4),
                    word_count=word_count,
                    extraction=_score_extraction(rec["doc_type"], text, lines, rec["fields"]),
                )
                print(
                    f"[paddleocr] ({i}/{len(records)}) {sid} OK in {elapsed:.2f}s, "
                    f"{len(text)} chars, {word_count} words, conf={conf:.3f}",
                    flush=True,
                )
            except FutureTimeoutError:
                elapsed = time.time() - t0
                entry.update(
                    timed_out=True,
                    elapsed_seconds=round(elapsed, 3),
                    error=f"Timed out after {PER_DOCUMENT_TIMEOUT_SECONDS}s (soft timeout - "
                    "the worker thread could not be force-killed and may still be running "
                    "in the background; this document was abandoned, not corrupted).",
                )
                print(
                    f"[paddleocr] ({i}/{len(records)}) {sid} TIMED OUT after "
                    f"{PER_DOCUMENT_TIMEOUT_SECONDS}s - moving on",
                    flush=True,
                )
            except Exception as exc:
                elapsed = time.time() - t0
                entry.update(elapsed_seconds=round(elapsed, 3), error=repr(exc))
                print(f"[paddleocr] ({i}/{len(records)}) {sid} FAILED: {exc!r}", flush=True)
            per_document.append(entry)
    finally:
        # Do not block process exit waiting on a stuck worker thread from a
        # timed-out call - daemon-style abandonment, not a clean join.
        executor.shutdown(wait=False, cancel_futures=True)

    return {
        "engine": "paddleocr",
        "config": {"enable_mkldnn": False, "lang": "en"},
        "engine_load_failed": False,
        "engine_load_seconds": round(load_seconds, 2),
        "per_document_timeout_seconds": PER_DOCUMENT_TIMEOUT_SECONDS,
        "per_document": per_document,
    }


def bench_tesseract(records: list[dict]) -> dict:
    from app.docai.ocr import extract_text

    per_document = []
    for i, rec in enumerate(records, start=1):
        sid = rec["sample_id"]
        content = rec["image_path"].read_bytes()
        t0 = time.time()
        result = extract_text(content, "image/jpeg")
        elapsed = time.time() - t0
        entry = {
            "sample_id": sid,
            "doc_type": rec["doc_type"],
            "success": bool(result.text),
            "elapsed_seconds": round(elapsed, 3),
            "text_length": len(result.text),
            "ocr_confidence": result.mean_word_confidence,
            "word_count": result.word_count,
            "extraction": _score_extraction(
                rec["doc_type"], result.text, result.lines, rec["fields"]
            ),
        }
        per_document.append(entry)
        print(f"[tesseract] ({i}/{len(records)}) {sid} OK in {elapsed:.2f}s", flush=True)
    return {"engine": "tesseract", "per_document": per_document}


def bench_doctr(records: list[dict]) -> dict:
    print("[doctr] loading engine...", flush=True)
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor

    model = ocr_predictor(pretrained=True)
    per_document = []
    for i, rec in enumerate(records, start=1):
        sid = rec["sample_id"]
        t0 = time.time()
        doc = DocumentFile.from_images(str(rec["image_path"]))
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
                (_, ymin), (_, ymax) = line.geometry
                lines.append(
                    OcrLine(text=" ".join(words), top=int(ymin * page_h), bottom=int(ymax * page_h))
                )
        text = "\n".join(ln.text for ln in lines)
        elapsed = time.time() - t0
        entry = {
            "sample_id": sid,
            "doc_type": rec["doc_type"],
            "success": bool(text),
            "elapsed_seconds": round(elapsed, 3),
            "text_length": len(text),
            "ocr_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
            "word_count": len(words_all),
            "extraction": _score_extraction(rec["doc_type"], text, lines, rec["fields"]),
        }
        per_document.append(entry)
        print(f"[doctr] ({i}/{len(records)}) {sid} OK in {elapsed:.2f}s", flush=True)
    return {"engine": "doctr", "per_document": per_document}


def _summarize(per_document: list[dict]) -> dict:
    successes = [d for d in per_document if d.get("success")]
    latencies = [d["elapsed_seconds"] for d in successes if d.get("elapsed_seconds") is not None]
    field_results = []
    for d in successes:
        for _field_key, res in (d.get("extraction") or {}).items():
            field_results.append(res["match"])
    return {
        "n": len(per_document),
        "n_success": len(successes),
        "success_rate": round(len(successes) / len(per_document), 4) if per_document else None,
        "mean_latency_seconds": round(statistics.mean(latencies), 3) if latencies else None,
        "median_latency_seconds": round(statistics.median(latencies), 3) if latencies else None,
        "min_latency_seconds": round(min(latencies), 3) if latencies else None,
        "max_latency_seconds": round(max(latencies), 3) if latencies else None,
        "field_n": len(field_results),
        "field_exact_match_accuracy": round(sum(field_results) / len(field_results), 4)
        if field_results
        else None,
    }


def main() -> None:
    records = _load_records()
    print(
        f"Loaded {len(records)} representative documents (val split, real ground truth).",
        flush=True,
    )

    report: dict = {"sample_ids": SAMPLE_IDS, "engines": {}}

    print("\n=== TESSERACT (same 8 documents) ===", flush=True)
    tess = bench_tesseract(records)
    report["engines"]["tesseract"] = {**tess, "summary": _summarize(tess["per_document"])}

    print("\n=== DOCTR (same 8 documents) ===", flush=True)
    try:
        doctr = bench_doctr(records)
        report["engines"]["doctr"] = {**doctr, "summary": _summarize(doctr["per_document"])}
    except Exception as exc:
        print(f"[doctr] FAILED: {exc!r}", flush=True)
        report["engines"]["doctr"] = {"engine": "doctr", "failed": True, "error": repr(exc)}

    # Save after tesseract+doctr regardless of what happens to paddleocr -
    # per requirement 8, a partial report must still be written.
    reports_dir = DATASET_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    out_path = reports_dir / "ocr_bench_small_8doc.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\n[checkpoint] partial report saved to {out_path}", flush=True)

    print("\n=== PADDLEOCR (same 8 documents, enable_mkldnn=False) ===", flush=True)
    try:
        paddle = bench_paddleocr(records)
        report["engines"]["paddleocr"] = {**paddle, "summary": _summarize(paddle["per_document"])}
    except Exception as exc:
        print(f"[paddleocr] FAILED (outer): {exc!r}", flush=True)
        report["engines"]["paddleocr"] = {"engine": "paddleocr", "failed": True, "error": repr(exc)}

    out_path.write_text(json.dumps(report, indent=2))
    print(f"\n[final] full report saved to {out_path}", flush=True)

    print("\n=== SUMMARY ===", flush=True)
    for engine_name, data in report["engines"].items():
        s = data.get("summary")
        if s:
            print(
                f"{engine_name:12s} n={s['n']} success_rate={s['success_rate']} "
                f"mean_lat={s['mean_latency_seconds']}s median_lat={s['median_latency_seconds']}s "
                f"field_acc={s['field_exact_match_accuracy']} (n_fields={s['field_n']})",
                flush=True,
            )
        else:
            print(f"{engine_name:12s} FAILED: {data.get('error')}", flush=True)


if __name__ == "__main__":
    main()
