"""Synthetic document generator for the INVESTMENT pack's real evidence
doc types (CANCELLED_CHEQUE, BANK_STATEMENT_SUMMARY, KRA_KYC_LETTER),
sourced from `app/packs/manifests/investment.yaml` evidence_mappings.

`KRA_KYC_LETTER` reuses the same real Indian PAN format as Credit Card's
`ITR_V_ACKNOWLEDGEMENT` and Account Opening's `PAN_CARD_IMAGE` - a real,
unavoidable overlap in identifier SHAPE (all three are the one real PAN
format), not a copy: this file generates its own independent synthetic
content, its own dataset/model artifacts under `data/docai/investment/`
and `investment_classifier.joblib`. `CANCELLED_CHEQUE`'s IFSC code and
`BANK_STATEMENT_SUMMARY`'s account number are both genuinely new
identifier shapes for this journey.

Run: `uv run python -m app.docai.dataset.generate_investment`
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

DATASET_ROOT = Path(__file__).resolve().parents[3] / "data" / "docai" / "investment"
SEED = 20260919  # distinct from every other journey's seed

BANK_NAMES = [
    "Kotak Metro Bank",
    "Unity Cooperative Bank",
    "Sundar National Bank",
    "Meridian Trust Bank",
]
BANK_CODE_LETTERS = ["KMBL", "UNCB", "SUNB", "MTBL"]


def _rand_pan(rng: random.Random) -> str:
    # Real Indian PAN format: 5 letters + 4 digits + 1 letter.
    letters1 = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(5))
    digits = "".join(str(rng.randint(0, 9)) for _ in range(4))
    letter2 = rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"{letters1}{digits}{letter2}"


def _rand_ifsc(rng: random.Random) -> str:
    # Real IFSC format: 4-letter bank code + fixed "0" + 6-digit branch code.
    bank_code = rng.choice(BANK_CODE_LETTERS)
    branch = "".join(str(rng.randint(0, 9)) for _ in range(6))
    return f"{bank_code}0{branch}"


def _rand_account_number(rng: random.Random) -> str:
    # 12-digit account number (this dataset's own fixed convention - real
    # Indian bank account numbers vary in length bank to bank, disclosed
    # in extraction.py rather than treated as one universal standard).
    return "".join(str(rng.randint(0, 9)) for _ in range(12))


def _make_fields(rng: random.Random, fake: Faker, doc_type: str) -> dict:
    idx = rng.randrange(len(BANK_NAMES))
    return {
        "name": fake.name(),
        "pan": _rand_pan(rng),
        "ifsc": _rand_ifsc(rng),
        "account_number": _rand_account_number(rng),
        "bank_name": BANK_NAMES[idx],
        "branch": fake.city() + " Branch",
        "statement_period": fake.date(pattern="%b %Y"),
        "kra_reg_date": fake.date(pattern="%d/%m/%Y"),
        "cheque_number": f"{rng.randint(100000, 999999)}",
    }


def _draw_cancelled_cheque(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "cheque_standard":
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 18 * mm, f["bank_name"])
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 24 * mm, f["branch"])
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 36 * mm, f"Pay: {f['name']}")
        c.drawString(20 * mm, h - 43 * mm, "CANCELLED")
        c.drawString(20 * mm, h - 52 * mm, f"IFSC Code: {f['ifsc']}")
        c.drawString(20 * mm, h - 59 * mm, f"A/c No: {f['account_number']}")
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 66 * mm, f"Cheque No: {f['cheque_number']}")
    elif template == "cheque_compact":
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, f["bank_name"] + " - CANCELLED")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Name: {f['name']}  IFSC {f['ifsc']}")
        c.drawString(20 * mm, h - 35 * mm, f"A/c No: {f['account_number']}")
    else:  # cheque_letterhead_unseen
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, h - 18 * mm, f["bank_name"].upper())
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 34 * mm, f"This cancelled cheque belongs to {f['name']},")
        c.drawString(20 * mm, h - 40 * mm, f"IFSC Code {f['ifsc']}, held at {f['branch']}.")
        c.drawString(20 * mm, h - 47 * mm, f"A/c No: {f['account_number']}")


def _draw_bank_statement(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "statement_standard":
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(w / 2, h - 20 * mm, f["bank_name"])
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 32 * mm, "ACCOUNT STATEMENT SUMMARY")
        c.drawString(20 * mm, h - 42 * mm, f"Account Holder: {f['name']}")
        c.drawString(20 * mm, h - 49 * mm, f"Account No: {f['account_number']}")
        c.drawString(20 * mm, h - 56 * mm, f"Statement Period: {f['statement_period']}")
    elif template == "statement_compact":
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, "Account Statement Summary")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Name: {f['name']}  Account No {f['account_number']}")
        c.drawString(20 * mm, h - 35 * mm, f"Statement Period: {f['statement_period']}")
    else:  # statement_letterhead_unseen
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, h - 18 * mm, f["bank_name"].upper() + " - CUSTOMER SERVICES")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 34 * mm, f"This statement summary is issued for {f['name']},")
        c.drawString(20 * mm, h - 40 * mm, f"Account No {f['account_number']}.")
        c.drawString(20 * mm, h - 47 * mm, f"Statement Period: {f['statement_period']}")


def _draw_kra_letter(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "kra_standard":
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(w / 2, h - 18 * mm, "KYC REGISTRATION AGENCY")
        c.setFont("Helvetica", 8)
        c.drawCentredString(w / 2, h - 24 * mm, "SEBI Registered Intermediary")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 36 * mm, f"Investor Name: {f['name']}")
        c.drawString(20 * mm, h - 43 * mm, f"PAN: {f['pan']}")
        c.drawString(20 * mm, h - 50 * mm, f"Date of Registration: {f['kra_reg_date']}")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 59 * mm, "KYC Status: VALIDATED")
    elif template == "kra_compact":
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, "KRA KYC Validation Letter")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Name: {f['name']}  PAN {f['pan']}")
        c.drawString(20 * mm, h - 35 * mm, f"Registered on: {f['kra_reg_date']}")
    else:  # kra_letterhead_unseen
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, h - 18 * mm, "CENTRAL KYC REGISTRY - INTERMEDIARY NOTICE")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 34 * mm, f"This letter certifies that {f['name']} holds")
        c.drawString(20 * mm, h - 40 * mm, f"a valid KRA KYC record under PAN {f['pan']}.")
        c.drawString(20 * mm, h - 47 * mm, f"Date of Issue: {f['kra_reg_date']}")


def _draw_other(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 20 * mm, "QuickBuy Electronics - Invoice")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 30 * mm, f"Invoice No: INV-{f['account_number'][-5:]}")
    c.drawString(20 * mm, h - 36 * mm, f"Customer: {f['name']}")
    y = h - 50 * mm
    for item, amt in [("Headphones", 1800), ("Charger", 600), ("Total", 2400)]:
        c.drawString(20 * mm, y, item)
        c.drawRightString(100 * mm, y, str(amt))
        y -= 7 * mm


TEMPLATES: dict[str, list[str]] = {
    "CANCELLED_CHEQUE": ["cheque_standard", "cheque_compact", "cheque_letterhead_unseen"],
    "BANK_STATEMENT_SUMMARY": [
        "statement_standard",
        "statement_compact",
        "statement_letterhead_unseen",
    ],
    "KRA_KYC_LETTER": ["kra_standard", "kra_compact", "kra_letterhead_unseen"],
    "OTHER": ["receipt"],
}
UNSEEN_TEMPLATE: dict[str, str] = {
    "CANCELLED_CHEQUE": "cheque_letterhead_unseen",
    "BANK_STATEMENT_SUMMARY": "statement_letterhead_unseen",
    "KRA_KYC_LETTER": "kra_letterhead_unseen",
}

DRAW_FN = {
    "CANCELLED_CHEQUE": _draw_cancelled_cheque,
    "BANK_STATEMENT_SUMMARY": _draw_bank_statement,
    "KRA_KYC_LETTER": _draw_kra_letter,
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
        if doc_type == "CANCELLED_CHEQUE":
            gt_fields["identifier"] = fields["ifsc"]
        elif doc_type == "BANK_STATEMENT_SUMMARY":
            gt_fields["identifier"] = fields["account_number"]
            gt_fields["document_date"] = fields["statement_period"]
        elif doc_type == "KRA_KYC_LETTER":
            gt_fields["identifier"] = fields["pan"]
            gt_fields["document_date"] = fields["kra_reg_date"]

        label = DocumentLabel(
            sample_id=sample_id,
            journey_type="INVESTMENT",
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

    for doc_type in ["CANCELLED_CHEQUE", "BANK_STATEMENT_SUMMARY", "KRA_KYC_LETTER"]:
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
                journey_type="INVESTMENT",
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
