"""Lightweight pretrained DL field-EXTRACTION candidate vs the
deterministic label-anchored regex baseline - mission task 4. This is
NOT the classification benchmark (bench_dl_classifier.py, already done) -
that measures document TYPE; this measures whether a small pretrained
model can extract the actual FIELD VALUE (monthly_income / employer_name)
better than the current deterministic extractor.

Approach: zero-shot extractive question-answering with
`distilbert-base-cased-distilled-squad` (66M params, Apache-2.0,
https://huggingface.co/distilbert-base-cased-distilled-squad) - a
standard, small, pretrained SQuAD-tuned span-extraction model. Chosen
over training a token-classification/NER model from scratch because
there is no token-level BIO-labeled training data for this task (building
one would be a substantial new annotation effort, not a "lightweight
evaluation"); zero-shot QA needs no training at all, matching the
"evaluate whether a PRETRAINED model helps" framing - not a from-scratch
architecture choice.

Same OCR'd text and same frozen ground truth the deterministic baseline
uses - the only thing being compared is field VALUE extraction, not OCR.

Run in the isolated `.venv-ocr-bench` environment, ALONE (no concurrent
pytest/training jobs):
    .venv-ocr-bench/Scripts/python.exe app/docai/bench_dl_extraction.py [--full]

Default runs the same small 8-document representative subset as
bench_ocr_paddleocr_small.py, for the same reason (verify it is not
impractically slow before committing to the full 111-document set).
Pass --full to run the full frozen val/test/unseen_template dataset.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.docai.dataset.generate import DATASET_ROOT  # noqa: E402
from app.docai.normalize import normalize_indian_amount  # noqa: E402

MODEL_NAME = "distilbert-base-cased-distilled-squad"

QUESTIONS = {
    "SALARY_SLIP": "What is the net pay?",
    "BANK_STATEMENT": "What is the salary credit amount?",
    "OFFICE_ID_CARD": "What is the name of the employer company?",
    "OFFER_LETTER": "What is the name of the employer company?",
}

SMALL_SAMPLE_IDS = [
    "SALARY_SLIP_salary_table_0031",
    "SALARY_SLIP_salary_table_0032",
    "BANK_STATEMENT_bank_hdfc_0091",
    "BANK_STATEMENT_bank_hdfc_0093",
    "OFFICE_ID_CARD_id_horizontal_0141",
    "OFFICE_ID_CARD_id_horizontal_0142",
    "OFFER_LETTER_offer_formal_0185",
    "OFFER_LETTER_offer_formal_0186",
]


def _load_all_records() -> list[dict]:
    records = []
    for split in ("val", "test", "unseen_template"):
        split_dir = DATASET_ROOT / split
        labels_path = split_dir / "labels.jsonl"
        ocr_path = split_dir / "ocr_cache.jsonl"
        if not labels_path.exists() or not ocr_path.exists():
            continue
        labels = {}
        with labels_path.open(encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                labels[rec["sample_id"]] = rec
        ocr = {}
        with ocr_path.open(encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                ocr[rec["sample_id"]] = rec
        for sid, label in labels.items():
            if sid in ocr and label["doc_type"] not in ("UNREADABLE", "OTHER"):
                records.append({**label, "split": split, "text": ocr[sid]["text"]})
    return records


def _score(doc_type: str, field_key: str, gt_value, predicted_raw: str | None) -> dict:
    if field_key == "monthly_income":
        predicted = normalize_indian_amount(predicted_raw) if predicted_raw else None
        is_match = predicted == gt_value
    else:
        predicted = predicted_raw
        is_match = bool(predicted) and (
            str(gt_value).lower() in str(predicted).lower()
            or str(predicted).lower() in str(gt_value).lower()
        )
    return {
        "expected": gt_value,
        "predicted_raw": predicted_raw,
        "predicted": predicted,
        "match": is_match,
    }


def _load_qa_model():
    """Loads the model/tokenizer directly rather than via
    `transformers.pipeline("question-answering", ...)`: that high-level
    task alias was removed in transformers 5.17.0 (installed here) -
    `pipeline(...)` raises `KeyError: "Unknown task question-answering"`,
    confirmed directly against this environment's installed version, not
    assumed. `document-question-answering` and `table-question-answering`
    remain, but plain extractive QA over text does not, at least under
    that name in this release. Using AutoModelForQuestionAnswering +
    AutoTokenizer directly with manual span decoding sidesteps the
    pipeline registry entirely and is the standard low-level way to do
    the exact same computation.
    """
    import torch
    from transformers import AutoModelForQuestionAnswering, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForQuestionAnswering.from_pretrained(MODEL_NAME)
    model.eval()

    def qa(question: str, context: str) -> dict:
        inputs = tokenizer(question, context, return_tensors="pt", truncation=True, max_length=384)
        with torch.no_grad():
            outputs = model(**inputs)
        start_idx = int(torch.argmax(outputs.start_logits))
        end_idx = int(torch.argmax(outputs.end_logits))
        if end_idx < start_idx:
            end_idx = start_idx
        answer_tokens = inputs["input_ids"][0][start_idx : end_idx + 1]
        answer = tokenizer.decode(answer_tokens, skip_special_tokens=True).strip()
        start_score = float(torch.softmax(outputs.start_logits, dim=-1)[0][start_idx])
        end_score = float(torch.softmax(outputs.end_logits, dim=-1)[0][end_idx])
        return {"answer": answer, "score": (start_score + end_score) / 2}

    return qa


def run(full: bool) -> dict:
    print(f"[dl_extraction] loading {MODEL_NAME}...", flush=True)

    t0 = time.time()
    qa = _load_qa_model()
    load_seconds = time.time() - t0
    print(f"[dl_extraction] loaded in {load_seconds:.1f}s (CPU)", flush=True)

    if full:
        records = _load_all_records()
    else:
        all_recs = {r["sample_id"]: r for r in _load_all_records()}
        records = [all_recs[sid] for sid in SMALL_SAMPLE_IDS if sid in all_recs]

    print(f"[dl_extraction] evaluating {len(records)} documents...", flush=True)

    per_document = []
    for i, rec in enumerate(records, start=1):
        doc_type = rec["doc_type"]
        question = QUESTIONS[doc_type]
        field_key = (
            "monthly_income" if doc_type in ("SALARY_SLIP", "BANK_STATEMENT") else "employer_name"
        )
        gt_value = rec["fields"].get(field_key)

        t0 = time.time()
        try:
            result = qa(question=question, context=rec["text"][:2000])
            answer = result.get("answer")
            qa_score = result.get("score")
            error = None
        except Exception as exc:
            answer, qa_score, error = None, None, repr(exc)
        elapsed = time.time() - t0

        scored = _score(doc_type, field_key, gt_value, answer) if gt_value is not None else None
        entry = {
            "sample_id": rec["sample_id"],
            "split": rec["split"],
            "doc_type": doc_type,
            "field_key": field_key,
            "question": question,
            "elapsed_seconds": round(elapsed, 3),
            "qa_answer": answer,
            "qa_score": round(qa_score, 4) if qa_score is not None else None,
            "error": error,
            "result": scored,
        }
        per_document.append(entry)
        status = "MATCH" if (scored and scored["match"]) else ("NO-MATCH" if scored else "N/A")
        print(
            f"[dl_extraction] ({i}/{len(records)}) {rec['sample_id']} "
            f"[{elapsed:.2f}s] answer={answer!r} score={qa_score} -> {status}",
            flush=True,
        )

    matched = [e for e in per_document if e["result"] and e["result"]["match"]]
    scored_entries = [e for e in per_document if e["result"] is not None]
    latencies = [e["elapsed_seconds"] for e in per_document]

    summary_by_field: dict[str, dict] = {}
    for field_key in ("monthly_income", "employer_name"):
        field_entries = [e for e in scored_entries if e["field_key"] == field_key]
        field_matches = [e for e in field_entries if e["result"]["match"]]
        summary_by_field[field_key] = {
            "n": len(field_entries),
            "exact_match_accuracy": round(len(field_matches) / len(field_entries), 4)
            if field_entries
            else None,
        }

    out = {
        "model": MODEL_NAME,
        "approach": "zero-shot extractive QA (no training)",
        "device": "cpu",
        "load_seconds": round(load_seconds, 2),
        "n_documents": len(per_document),
        "overall_exact_match_accuracy": round(len(matched) / len(scored_entries), 4)
        if scored_entries
        else None,
        "by_field": summary_by_field,
        "mean_latency_seconds": round(sum(latencies) / len(latencies), 4) if latencies else None,
        "per_document": per_document,
    }

    reports_dir = DATASET_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    suffix = "full" if full else "small8"
    out_path = reports_dir / f"dl_extraction_bench_{suffix}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"[dl_extraction] report saved to {out_path}", flush=True)
    return out


if __name__ == "__main__":
    full_run = "--full" in sys.argv
    result = run(full_run)
    print("\n=== SUMMARY ===", flush=True)
    print(f"overall_exact_match_accuracy={result['overall_exact_match_accuracy']}", flush=True)
    for field_key, s in result["by_field"].items():
        print(
            f"  {field_key}: n={s['n']} exact_match_accuracy={s['exact_match_accuracy']}",
            flush=True,
        )
    print(f"mean_latency_seconds={result['mean_latency_seconds']}", flush=True)
