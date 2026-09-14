"""Synthetic document generator for the ACCOUNT_OPENING pack's real evidence
doc types (SIGNATURE_SPECIMEN, PAN_CARD_IMAGE, AADHAAR_FRONT_BACK), sourced
from `app/packs/manifests/account_opening.yaml` evidence_mappings.

`PAN_CARD_IMAGE` uses the same real Indian PAN format as Credit Card's
`ITR_V_ACKNOWLEDGEMENT` - a real, unavoidable overlap in identifier SHAPE
(both are the one real PAN format), not a copy: this file generates its own
independent synthetic content, its own dataset/model artifacts under
`data/docai/account_opening/` and `account_opening_classifier.joblib`.
`AADHAAR_FRONT_BACK` is a genuinely new identifier shape (12 digits, no
letters at all) with no equivalent in any prior journey.
`SIGNATURE_SPECIMEN` is a genuinely new DOCUMENT shape too: unlike every
prior doc type, its real-world content is mostly a handwritten mark, not
printed text - classification here leans almost entirely on the sparse
printed label/header text a specimen signature card or sheet actually
carries, which is realistic (a signature capture form still prints a
header/label even though the signature itself isn't OCR-readable text).

Run: `uv run python -m app.docai.dataset.generate_account_opening`
"""

from __future__ import annotations

import io
import json
import random
from pathlib import Path

import pymupdf
from faker import Faker
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.docai.dataset.generate import _degrade
from app.docai.dataset.schema import DocumentLabel

DATASET_ROOT = Path(__file__).resolve().parents[3] / "data" / "docai" / "account_opening"
SEED = 20260918  # distinct from every other journey's seed


def _rand_pan(rng: random.Random) -> str:
    # Real Indian PAN format: 5 letters + 4 digits + 1 letter.
    letters1 = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(5))
    digits = "".join(str(rng.randint(0, 9)) for _ in range(4))
    letter2 = rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"{letters1}{digits}{letter2}"


def _rand_aadhaar(rng: random.Random) -> str:
    # Real Aadhaar format: 12 digits, printed in 3 groups of 4.
    groups = ["".join(str(rng.randint(0, 9)) for _ in range(4)) for _ in range(3)]
    return " ".join(groups)


def _seed_from_name(name: str) -> random.Random:
    """A small deterministic per-document RNG for the signature squiggle's
    shape, derived from the field values themselves (not Python's
    randomized `hash()`, which is salted per-process and would make the
    dataset non-reproducible run to run even under a fixed top-level
    seed)."""
    return random.Random(sum(ord(ch) for ch in name) & 0xFFFF)


def _draw_signature_squiggle(c: canvas.Canvas, x: float, y: float, rng: random.Random) -> None:
    """Draws a wavy line to stand in for a handwritten signature mark -
    genuinely not OCR-readable text (as a real signature isn't), so no
    ground-truth field is ever attached to its content."""
    c.saveState()
    c.setLineWidth(1.2)
    px, py = x, y
    for _ in range(6):
        nx = px + rng.uniform(8, 16)
        ny = y + rng.uniform(-6, 6)
        c.line(px, py, nx, ny)
        px, py = nx, ny
    c.restoreState()


def _make_fields(rng: random.Random, fake: Faker, doc_type: str) -> dict:
    return {
        "name": fake.name(),
        "pan": _rand_pan(rng),
        "aadhaar": _rand_aadhaar(rng),
        "dob": fake.date(pattern="%d/%m/%Y"),
        "signature_date": fake.date(pattern="%d/%m/%Y"),
        "address": f"{fake.street_address()}, {fake.city()}",
    }


def _draw_signature_specimen(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "signature_card":
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(w / 2, h - 20 * mm, "SPECIMEN SIGNATURE CARD")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 32 * mm, f"Account Holder Name: {f['name']}")
        c.drawString(20 * mm, h - 39 * mm, f"Date: {f['signature_date']}")
        c.rect(20 * mm, h - 65 * mm, 80 * mm, 18 * mm)
        _draw_signature_squiggle(c, 28 * mm, h - 56 * mm, _seed_from_name(f["name"]))
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 68 * mm, "Signature")
    elif template == "signature_labeled":
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 18 * mm, "Specimen Signature")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 26 * mm, f"Name: {f['name']}")
        _draw_signature_squiggle(c, 25 * mm, h - 42 * mm, _seed_from_name(f["name"]))
    else:  # signature_plain_unseen - deliberately sparse, hardest case
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 15 * mm, "Signature:")
        _draw_signature_squiggle(c, 22 * mm, h - 30 * mm, _seed_from_name(f["name"]))
        c.setFont("Helvetica", 7)
        c.drawString(22 * mm, h - 38 * mm, f["name"])


def _draw_pan_card(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "pan_standard":
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(w / 2, h - 18 * mm, "INCOME TAX DEPARTMENT")
        c.setFont("Helvetica", 8)
        c.drawCentredString(w / 2, h - 24 * mm, "GOVT. OF INDIA")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 36 * mm, f"Name: {f['name']}")
        c.drawString(20 * mm, h - 43 * mm, f"Date of Birth: {f['dob']}")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 52 * mm, f"PAN: {f['pan']}")
    elif template == "pan_compact":
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, "Permanent Account Number Card")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Name: {f['name']}  PAN {f['pan']}")
        c.drawString(20 * mm, h - 35 * mm, f"DOB: {f['dob']}")
    else:  # pan_letterhead_unseen
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, h - 18 * mm, "GOVERNMENT OF INDIA - INCOME TAX DEPARTMENT")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 34 * mm, f"This card certifies that {f['name']} holds")
        c.drawString(20 * mm, h - 40 * mm, f"Permanent Account Number {f['pan']}.")
        c.drawString(20 * mm, h - 47 * mm, f"Date of Birth: {f['dob']}")


def _draw_aadhaar(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "aadhaar_standard":
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(w / 2, h - 18 * mm, "GOVERNMENT OF INDIA")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 30 * mm, f"Name: {f['name']}")
        c.drawString(20 * mm, h - 37 * mm, f"Date of Birth: {f['dob']}")
        c.drawString(20 * mm, h - 44 * mm, f"Address: {f['address']}")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 53 * mm, f"Aadhaar No: {f['aadhaar']}")
    elif template == "aadhaar_compact":
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, "Aadhaar")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Name: {f['name']}  Aadhaar {f['aadhaar']}")
        c.drawString(20 * mm, h - 35 * mm, f"DOB: {f['dob']}")
    else:  # aadhaar_letterhead_unseen
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, h - 18 * mm, "UNIQUE IDENTIFICATION AUTHORITY OF INDIA")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 34 * mm, f"This is to certify that {f['name']},")
        c.drawString(20 * mm, h - 40 * mm, f"Aadhaar Number {f['aadhaar']}, resides at")
        c.drawString(20 * mm, h - 46 * mm, f"{f['address']}.")
        c.drawString(20 * mm, h - 53 * mm, f"Date of Birth: {f['dob']}")


def _draw_other(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 20 * mm, "QuickBuy Electronics - Invoice")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 30 * mm, f"Invoice No: INV-{f['aadhaar'][-5:].replace(' ', '')}")
    c.drawString(20 * mm, h - 36 * mm, f"Customer: {f['name']}")
    y = h - 50 * mm
    for item, amt in [("Headphones", 1800), ("Charger", 600), ("Total", 2400)]:
        c.drawString(20 * mm, y, item)
        c.drawRightString(100 * mm, y, str(amt))
        y -= 7 * mm


TEMPLATES: dict[str, list[str]] = {
    "SIGNATURE_SPECIMEN": ["signature_card", "signature_labeled", "signature_plain_unseen"],
    "PAN_CARD_IMAGE": ["pan_standard", "pan_compact", "pan_letterhead_unseen"],
    "AADHAAR_FRONT_BACK": ["aadhaar_standard", "aadhaar_compact", "aadhaar_letterhead_unseen"],
    "OTHER": ["receipt"],
}
UNSEEN_TEMPLATE: dict[str, str] = {
    "SIGNATURE_SPECIMEN": "signature_plain_unseen",
    "PAN_CARD_IMAGE": "pan_letterhead_unseen",
    "AADHAAR_FRONT_BACK": "aadhaar_letterhead_unseen",
}

DRAW_FN = {
    "SIGNATURE_SPECIMEN": _draw_signature_specimen,
    "PAN_CARD_IMAGE": _draw_pan_card,
    "AADHAAR_FRONT_BACK": _draw_aadhaar,
    "OTHER": _draw_other,
}


def generate_dataset(
    n_per_template_train: int = 10,
    n_per_template_val: int = 3,
    n_per_template_test: int = 3,
    n_unseen: int = 12,
    n_other: int = 15,
    n_unreadable: int = 6,
) -> Path:
    rng = random.Random(SEED)
    fake = Faker()
    Faker.seed(SEED)

    for split in ("train", "val", "test", "unseen_template"):
        (DATASET_ROOT / split).mkdir(parents=True, exist_ok=True)

    labels: dict[str, list[DocumentLabel]] = {
        "train": [],
        "val": [],
        "test": [],
        "unseen_template": [],
    }
    counter = 0

    def _render_and_save(doc_type: str, template: str, fields: dict, split: str) -> DocumentLabel:
        nonlocal counter
        counter += 1
        sample_id = f"{doc_type}_{template}_{counter:04d}"

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        DRAW_FN[doc_type](c, fields, template)
        c.showPage()
        c.save()
        pdf_bytes = buf.getvalue()

        split_dir = DATASET_ROOT / split
        pdf_path = split_dir / f"{sample_id}.pdf"
        pdf_path.write_bytes(pdf_bytes)

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pix = doc[0].get_pixmap(dpi=150)
        pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
        degraded, deg_info = _degrade(pil_img, rng)
        image_path = split_dir / f"{sample_id}.jpg"
        degraded.save(image_path, format="JPEG", quality=deg_info["jpeg_quality"])

        gt_fields: dict = {"name": fields["name"]}
        if doc_type == "PAN_CARD_IMAGE":
            gt_fields["identifier"] = fields["pan"]
            gt_fields["document_date"] = fields["dob"]
        elif doc_type == "AADHAAR_FRONT_BACK":
            gt_fields["identifier"] = fields["aadhaar"]
            gt_fields["document_date"] = fields["dob"]
        # SIGNATURE_SPECIMEN: name only - the signature mark itself carries
        # no extractable text, by design (see module docstring).

        label = DocumentLabel(
            sample_id=sample_id,
            journey_type="ACCOUNT_OPENING",
            doc_type=doc_type,
            template_id=template,
            split=split,
            image_path=str(image_path.relative_to(DATASET_ROOT)),
            pdf_path=str(pdf_path.relative_to(DATASET_ROOT)),
            fields=gt_fields,
            degradation=deg_info,
        )
        labels[split].append(label)
        return label

    for doc_type in ["SIGNATURE_SPECIMEN", "PAN_CARD_IMAGE", "AADHAAR_FRONT_BACK"]:
        templates = TEMPLATES[doc_type]
        unseen_tpl = UNSEEN_TEMPLATE[doc_type]
        train_templates = [t for t in templates if t != unseen_tpl]

        for split, n_per in [
            ("train", n_per_template_train),
            ("val", n_per_template_val),
            ("test", n_per_template_test),
        ]:
            for template in train_templates:
                for _ in range(n_per):
                    fields = _make_fields(rng, fake, doc_type)
                    _render_and_save(doc_type, template, fields, split)

        for _ in range(n_unseen):
            fields = _make_fields(rng, fake, doc_type)
            _render_and_save(doc_type, unseen_tpl, fields, "unseen_template")

    for split, n in [
        ("train", n_other),
        ("val", max(3, n_other // 4)),
        ("test", max(3, n_other // 4)),
        ("unseen_template", max(3, n_other // 5)),
    ]:
        for _ in range(n):
            fields = _make_fields(rng, fake, "OTHER")
            _render_and_save("OTHER", "receipt", fields, split)

    for i in range(n_unreadable):
        counter += 1
        sample_id = f"UNREADABLE_{counter:04d}"
        pil_img = Image.new("RGB", (1240, 1754), color=(255, 255, 255))
        if i % 2 == 1:
            import numpy as np

            arr = (np.random.default_rng(SEED + i).integers(0, 255, (1754, 1240, 3))).astype(
                "uint8"
            )
            pil_img = Image.fromarray(arr)
        image_path = DATASET_ROOT / "test" / f"{sample_id}.jpg"
        pil_img.save(image_path, format="JPEG", quality=40)
        labels["test"].append(
            DocumentLabel(
                sample_id=sample_id,
                journey_type="ACCOUNT_OPENING",
                doc_type="UNREADABLE",
                template_id="blank_or_noise",
                split="test",
                image_path=str(image_path.relative_to(DATASET_ROOT)),
                pdf_path=None,
                fields={},
                degradation={"synthetic": "blank_or_noise"},
            )
        )

    for split, items in labels.items():
        out = DATASET_ROOT / split / "labels.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for label in items:
                f.write(label.model_dump_json() + "\n")

    manifest = {split: len(items) for split, items in labels.items()}
    (DATASET_ROOT / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2))
    return DATASET_ROOT


if __name__ == "__main__":
    root = generate_dataset()
    print(f"Dataset written to {root}")
    print(json.dumps(json.loads((root / "dataset_manifest.json").read_text()), indent=2))
