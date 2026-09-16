"""Document classification + wrong-document detection.

A genuinely trained statistical model (TF-IDF word/char n-gram features ->
multinomial logistic regression), not an `if keyword in text` rule. It
learns weighted associations between n-grams and doc_type from the
training set, which is why it can, for example, tell a bank statement
from a salary slip using the whole distribution of words on the page
(bank name, "account", "IFSC", transaction-table wording) rather than a
single hand-picked trigger word - and it is honestly evaluated (see
docai/train_classifier.py) against a held-out unseen-template split
specifically to check it isn't just memorizing one layout's boilerplate.

Model choice rationale (mission Phase 2): the actual task here is
closed-set classification over a small, well-defined list of doc_types
per journey (an manifest's evidence_mappings, never an open-ended
document universe). A lightweight linear text classifier is the
appropriate, honestly-evaluable choice for that task on this hardware
(no GPU dependency, sub-millisecond inference, trains in seconds) - a
multi-billion-parameter vision-language model would be both unverifiable
(no capacity to actually benchmark it meaningfully here) and unnecessary
for a closed 5-class problem. If per-journey doc_type sets grow large or
visually similar enough that text content alone is ambiguous, a
layout-aware model becomes the next real candidate to evaluate - not a
default.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib

MODELS_DIR = Path(__file__).resolve().parent / "models"

# Below this OCR word-confidence, we do not trust the classifier's
# text-based prediction at all - report UNREADABLE_DOCUMENT instead of
# guessing. This is a design threshold, not a measured statistic; it is
# documented as such.
OCR_CONFIDENCE_FLOOR = 0.35
MIN_WORDS_FOR_CLASSIFICATION = 3

# Softmax margin below which we refuse to pick a single class.
AMBIGUOUS_MAX_PROBA_FLOOR = 0.45


@dataclass
class ClassificationResult:
    predicted_doc_type: str
    probabilities: dict[str, float]
    outcome: str  # CORRECT_DOCUMENT | WRONG_DOCUMENT | AMBIGUOUS_DOCUMENT | UNREADABLE_DOCUMENT
    reason: str


class DocumentClassifier:
    def __init__(self, pipeline, label_names: list[str], version: str):
        self.pipeline = pipeline
        self.label_names = label_names
        self.version = version

    @classmethod
    def load(cls, journey_type: str) -> DocumentClassifier | None:
        path = MODELS_DIR / f"{journey_type.lower()}_classifier.joblib"
        meta_path = MODELS_DIR / f"{journey_type.lower()}_classifier.meta.json"
        if not path.exists() or not meta_path.exists():
            return None
        pipeline = joblib.load(path)
        meta = json.loads(meta_path.read_text())
        return cls(pipeline=pipeline, label_names=meta["label_names"], version=meta["version"])

    def predict_proba(self, text: str) -> dict[str, float]:
        proba = self.pipeline.predict_proba([text])[0]
        return {label: float(p) for label, p in zip(self.pipeline.classes_, proba, strict=True)}

    def classify(
        self,
        text: str,
        expected_doc_type: str,
        ocr_confidence: float,
        word_count: int,
        accepted_doc_types: set[str] | None = None,
    ) -> ClassificationResult:
        """`accepted_doc_types`, when given, is the FULL set of doc_types
        that satisfy the same action as `expected_doc_type` (real manifest
        example: Lending's UPLOAD_INCOME_PROOF accepts either SALARY_SLIP
        or BANK_STATEMENT, independently mapped - see
        app/ai/models.py::AIInterpretationResult.resolved_doc_type for the
        full explanation). Defaults to `{expected_doc_type}` alone, which
        is byte-for-byte the previous single-type behavior - existing
        callers that never pass this parameter are unaffected."""
        if word_count < MIN_WORDS_FOR_CLASSIFICATION or ocr_confidence < OCR_CONFIDENCE_FLOOR:
            return ClassificationResult(
                predicted_doc_type="UNREADABLE",
                probabilities={},
                outcome="UNREADABLE_DOCUMENT",
                reason=(
                    f"OCR produced {word_count} word(s) at mean confidence "
                    f"{ocr_confidence:.2f} (floor {OCR_CONFIDENCE_FLOOR}); too little "
                    "reliable text to classify."
                ),
            )

        probabilities = self.predict_proba(text)
        predicted = max(probabilities, key=lambda k: probabilities[k])
        top_p = probabilities[predicted]

        if top_p < AMBIGUOUS_MAX_PROBA_FLOOR:
            return ClassificationResult(
                predicted_doc_type=predicted,
                probabilities=probabilities,
                outcome="AMBIGUOUS_DOCUMENT",
                reason=(
                    f"Top predicted class '{predicted}' has probability {top_p:.2f}, "
                    f"below the {AMBIGUOUS_MAX_PROBA_FLOOR} confidence floor."
                ),
            )

        acceptable = accepted_doc_types or {expected_doc_type.upper()}
        if predicted == "OTHER" or predicted not in acceptable:
            return ClassificationResult(
                predicted_doc_type=predicted,
                probabilities=probabilities,
                outcome="WRONG_DOCUMENT",
                reason=(
                    f"Expected '{expected_doc_type}' but classifier predicts "
                    f"'{predicted}' with probability {top_p:.2f}."
                ),
            )

        return ClassificationResult(
            predicted_doc_type=predicted,
            probabilities=probabilities,
            outcome="CORRECT_DOCUMENT",
            reason=f"Matches expected '{expected_doc_type}' with probability {top_p:.2f}.",
        )


_CLASSIFIER_CACHE: dict[str, DocumentClassifier | None] = {}


def get_classifier(journey_type: str) -> DocumentClassifier | None:
    if journey_type not in _CLASSIFIER_CACHE:
        _CLASSIFIER_CACHE[journey_type] = DocumentClassifier.load(journey_type)
    return _CLASSIFIER_CACHE[journey_type]
