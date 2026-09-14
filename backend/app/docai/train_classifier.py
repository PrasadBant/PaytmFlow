"""Trains and evaluates the LENDING document classifier.

Reports REAL measured metrics on val/test/unseen_template - nothing here
is invented. If you rerun this with a different dataset (different SEED
in dataset/generate.py, or more samples), the numbers will differ; that's
expected, and is exactly why this script exists rather than a metrics
report typed by hand.

Run: `uv run python -m app.docai.train_classifier`
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline

from app.docai.classifier import MODELS_DIR, DocumentClassifier
from app.docai.dataset.generate import DATASET_ROOT as LENDING_DATASET_ROOT
from app.docai.dataset.generate import SEED as LENDING_SEED

# Defaults preserve the exact original LENDING CLI behavior
# (`python -m app.docai.train_classifier`, no args) - the function itself
# is journey-agnostic: same TF-IDF+LogisticRegression mechanism, same
# metrics, reused verbatim for Insurance (and any future pack) by passing
# its own journey_type/dataset_root/seed, not by copying this file.
JOURNEY_TYPE = "LENDING"
MODEL_VERSION = "lending-classifier-v1"


def _load_split(split: str, dataset_root: Path) -> tuple[list[str], list[str], list[dict]]:
    """Returns (texts, labels, raw_records) for a split, joining labels.jsonl
    with ocr_cache.jsonl by sample_id."""
    split_dir = dataset_root / split
    labels = {}
    with (split_dir / "labels.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            labels[rec["sample_id"]] = rec

    ocr_by_id = {}
    with (split_dir / "ocr_cache.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            ocr_by_id[rec["sample_id"]] = rec

    texts, doc_types, raw = [], [], []
    for sample_id, label_rec in labels.items():
        ocr_rec = ocr_by_id.get(sample_id)
        if not ocr_rec:
            continue
        # UNREADABLE samples are intentionally excluded from classifier
        # training/accuracy scoring - they're a separate safe-path check
        # (docai/classifier.py's OCR-confidence floor), not a class the
        # text classifier is asked to discriminate.
        if label_rec["doc_type"] == "UNREADABLE":
            continue
        texts.append(ocr_rec["text"])
        doc_types.append(label_rec["doc_type"])
        raw.append({**label_rec, **ocr_rec})
    return texts, doc_types, raw


def train_and_evaluate(
    journey_type: str = JOURNEY_TYPE,
    dataset_root: Path = LENDING_DATASET_ROOT,
    model_version: str = MODEL_VERSION,
    seed: int = LENDING_SEED,
    representative_expected_doc_type: str | None = None,
) -> dict:
    train_texts, train_labels, _ = _load_split("train", dataset_root)
    val_texts, val_labels, val_raw = _load_split("val", dataset_root)
    test_texts, test_labels, test_raw = _load_split("test", dataset_root)
    unseen_texts, unseen_labels, unseen_raw = _load_split("unseen_template", dataset_root)

    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=1,
                    sublinear_tf=True,
                    lowercase=True,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=2000,
                    C=2.0,
                    class_weight="balanced",
                    random_state=seed,
                ),
            ),
        ]
    )
    pipeline.fit(train_texts, train_labels)

    def _eval(split_name: str, texts: list[str], labels: list[str]) -> dict:
        if not texts:
            return {"split": split_name, "n": 0}
        preds = pipeline.predict(texts)
        class_labels = sorted(set(labels) | set(preds))
        return {
            "split": split_name,
            "n": len(texts),
            "accuracy": round(float((preds == __import__("numpy").array(labels)).mean()), 4),
            "macro_f1": round(float(f1_score(labels, preds, average="macro", zero_division=0)), 4),
            "macro_precision": round(
                float(precision_score(labels, preds, average="macro", zero_division=0)), 4
            ),
            "macro_recall": round(
                float(recall_score(labels, preds, average="macro", zero_division=0)), 4
            ),
            "per_class_report": classification_report(
                labels, preds, labels=class_labels, output_dict=True, zero_division=0
            ),
            "confusion_matrix": {
                "labels": class_labels,
                "matrix": confusion_matrix(labels, preds, labels=class_labels).tolist(),
            },
        }

    results = {
        "val": _eval("val", val_texts, val_labels),
        "test": _eval("test", test_texts, test_labels),
        "unseen_template": _eval("unseen_template", unseen_texts, unseen_labels),
    }

    # Runtime-safety-aware evaluation: raw pipeline.predict() above is a
    # pure argmax and is what the "accuracy"/"macro_f1" numbers describe -
    # useful for comparing models - but it is NOT what actually ships.
    # In production, every prediction goes through
    # DocumentClassifier.classify(), which refuses to report a confident
    # answer below AMBIGUOUS_MAX_PROBA_FLOOR. A raw-argmax "error" whose
    # own predicted probability was already below that floor is NOT a
    # live defect - the deployed code already reports AMBIGUOUS_DOCUMENT
    # for it, a safe non-answer, not a wrong one. Reporting only the raw
    # number would materially overstate the system's real failure rate.
    live_classifier = DocumentClassifier(
        pipeline=pipeline, label_names=sorted(set(train_labels)), version=model_version
    )

    # `expected_doc_type="OTHER"` is not a real production scenario - no
    # manifest action ever requests an "OTHER" document, so classify()
    # is never legitimately called that way at runtime. "OTHER" ground-
    # truth samples exist purely to teach the classifier what junk looks
    # like; the realistic test for one is "does the system correctly
    # REJECT it when a specific real document was actually expected" -
    # so those samples are evaluated against a representative real
    # doc_type instead of against their own "OTHER" label, and success
    # for them means WRONG_DOCUMENT (correctly rejected), not
    # CORRECT_DOCUMENT. Defaults to the first non-OTHER training label
    # actually present in this journey's own dataset - never a
    # hardcoded Lending doc_type for a different journey's run.
    representative_expected = representative_expected_doc_type or next(
        (label for label in sorted(set(train_labels)) if label != "OTHER"), "OTHER"
    )

    def _eval_runtime_safety(split_name: str, raw_list: list[dict]) -> dict:
        if not raw_list:
            return {"split": split_name, "n": 0}
        outcomes = {
            "CORRECT_DOCUMENT": 0,
            "WRONG_DOCUMENT": 0,
            "AMBIGUOUS_DOCUMENT": 0,
            "UNREADABLE_DOCUMENT": 0,
        }
        false_rejections = []  # a genuinely valid document incorrectly refused
        false_acceptances = []  # a genuinely wrong/junk document incorrectly accepted
        for rec in raw_list:
            is_junk = rec["doc_type"] == "OTHER"
            expected = representative_expected if is_junk else rec["doc_type"]
            result = live_classifier.classify(
                text=rec["text"],
                expected_doc_type=expected,
                ocr_confidence=rec.get("mean_word_confidence", 0.0),
                word_count=rec.get("word_count", 0),
            )
            outcomes[result.outcome] = outcomes.get(result.outcome, 0) + 1

            example = {
                "sample_id": rec["sample_id"],
                "expected": expected,
                "actual_doc_type": rec["doc_type"],
                "predicted": result.predicted_doc_type,
                "top_probability": round(
                    result.probabilities.get(result.predicted_doc_type, 0.0), 4
                ),
            }
            if is_junk and result.outcome == "CORRECT_DOCUMENT":
                false_acceptances.append(example)
            elif not is_junk and result.outcome == "WRONG_DOCUMENT":
                false_rejections.append(example)
        n = len(raw_list)
        return {
            "split": split_name,
            "n": n,
            "outcomes": outcomes,
            "correct_rate": round(outcomes["CORRECT_DOCUMENT"] / n, 4),
            "false_rejection_rate": round(len(false_rejections) / n, 4),
            "false_acceptance_rate": round(len(false_acceptances) / n, 4),
            "safe_non_answer_rate": round(
                (outcomes["AMBIGUOUS_DOCUMENT"] + outcomes["UNREADABLE_DOCUMENT"]) / n, 4
            ),
            "false_rejections": false_rejections,
            "false_acceptances": false_acceptances,
        }

    runtime_safety = {
        "val": _eval_runtime_safety("val", val_raw),
        "test": _eval_runtime_safety("test", test_raw),
        "unseen_template": _eval_runtime_safety("unseen_template", unseen_raw),
    }

    # Per-sample error records for error analysis (mission Phase 19) -
    # only actual misclassifications, with the real predicted vs expected
    # label and the degradation conditions that were applied.
    errors = []
    for raw_list, texts, labels, split_name in [
        (test_raw, test_texts, test_labels, "test"),
        (unseen_raw, unseen_texts, unseen_labels, "unseen_template"),
    ]:
        if not texts:
            continue
        preds = pipeline.predict(texts)
        for rec, pred, actual in zip(raw_list, preds, labels, strict=True):
            if pred != actual:
                errors.append(
                    {
                        "split": split_name,
                        "sample_id": rec["sample_id"],
                        "template_id": rec.get("template_id"),
                        "expected": actual,
                        "predicted": pred,
                        "ocr_confidence": rec.get("mean_word_confidence"),
                        "word_count": rec.get("word_count"),
                        "degradation": rec.get("degradation"),
                    }
                )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"{journey_type.lower()}_classifier.joblib"
    meta_path = MODELS_DIR / f"{journey_type.lower()}_classifier.meta.json"
    joblib.dump(pipeline, model_path)

    meta = {
        "version": model_version,
        "journey_type": journey_type,
        "label_names": sorted(set(train_labels)),
        "trained_at": datetime.now(UTC).isoformat(),
        "dataset_seed": seed,
        "train_n": len(train_texts),
        "sklearn_version": sklearn.__version__,
        "python_version": sys.version,
        "platform": platform.platform(),
        "model_type": "TfidfVectorizer(1,2-gram) + LogisticRegression(class_weight=balanced)",
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    report = {"meta": meta, "results": results, "errors": errors, "runtime_safety": runtime_safety}
    reports_dir = dataset_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "classifier_metrics.json").write_text(json.dumps(report, indent=2, default=str))
    return report


if __name__ == "__main__":
    report = train_and_evaluate()
    for split, res in report["results"].items():
        if res.get("n"):
            print(
                f"{split:16s} n={res['n']:3d}  accuracy={res['accuracy']:.4f}  "
                f"macro_f1={res['macro_f1']:.4f}  macro_precision={res['macro_precision']:.4f}  "
                f"macro_recall={res['macro_recall']:.4f}"
            )
        else:
            print(f"{split:16s} n=0 (no samples)")
    print(
        f"\n{len(report['errors'])} raw-argmax misclassification(s) - "
        "see data/docai/lending/reports/classifier_metrics.json"
    )
    print("\n--- runtime-safety-aware (what actually ships, via classify()) ---")
    for split, res in report["runtime_safety"].items():
        if res.get("n"):
            print(
                f"{split:16s} n={res['n']:3d}  correct_rate={res['correct_rate']:.4f}  "
                f"false_rejection_rate={res['false_rejection_rate']:.4f}  "
                f"false_acceptance_rate={res['false_acceptance_rate']:.4f}  "
                f"safe_non_answer_rate={res['safe_non_answer_rate']:.4f}  "
                f"outcomes={res['outcomes']}"
            )
