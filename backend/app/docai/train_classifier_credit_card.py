"""Trains and evaluates the CREDIT_CARD document classifier, reusing the
SAME shared TF-IDF+LogisticRegression mechanism as every other journey
(`app.docai.train_classifier.train_and_evaluate`) - no duplicated
architecture, only Credit Card's own data/paths passed in.

Run: `uv run python -m app.docai.train_classifier_credit_card`
"""

from __future__ import annotations

from app.docai.dataset.generate_credit_card import DATASET_ROOT, SEED
from app.docai.train_classifier import train_and_evaluate

JOURNEY_TYPE = "CREDIT_CARD"
MODEL_VERSION = "credit-card-classifier-v1"

if __name__ == "__main__":
    report = train_and_evaluate(
        journey_type=JOURNEY_TYPE,
        dataset_root=DATASET_ROOT,
        model_version=MODEL_VERSION,
        seed=SEED,
        representative_expected_doc_type="SALARY_SLIP",
    )
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
        "see data/docai/credit_card/reports/classifier_metrics.json"
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
