"""Dataset label schema for the PaytmFlow document-intelligence dataset.

One JSON object per generated document, written as JSON Lines (one record
per line) to `<split>/labels.jsonl` under the dataset root. This is the
single source of ground truth used by both training and evaluation - the
evaluation code never re-derives a label from the document itself.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    journey_type: str
    doc_type: str
    """One of the manifest's real evidence_mappings.doc_type values, or
    "OTHER" for a deliberately unrelated negative example used to test
    wrong-document / out-of-set detection."""

    template_id: str
    """Which visual template (issuer/layout/wording variant) generated
    this sample. Used to build the unseen-template split: templates used
    in `unseen_template` never appear in train/val/test for that doc_type."""

    split: str  # train | val | test | unseen_template

    image_path: str
    """Degraded/rasterized JPEG - the primary artifact OCR actually reads.
    This is what exercises the real Tesseract OCR path, not the PDF text
    layer, so measured accuracy reflects genuine OCR + extraction, not a
    lucky vector-text shortcut."""

    pdf_path: str | None = None
    """Native-text-layer PDF twin of the same content, used to separately
    measure the "real digital PDF" extraction path (PyMuPDF text layer,
    no OCR needed) as its own reported metric, not conflated with OCR
    accuracy."""

    fields: dict[str, Any]
    """Ground-truth structured field values for this document, using the
    manifest's own field keys (e.g. monthly_income, employer_name) plus
    auxiliary fields used only for cross-document consistency checks
    (name, document_date). Never invented fields outside what the
    generator actually rendered onto the document."""

    degradation: dict[str, Any]
    """What was applied to the image (rotation_deg, jpeg_quality, noise_sigma,
    blur_radius) - recorded so error analysis can correlate failures with
    document-quality conditions (mission Phase 19)."""


def label_to_jsonl_row(label: DocumentLabel) -> str:
    return label.model_dump_json()
