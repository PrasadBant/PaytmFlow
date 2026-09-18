"""Synthetic document generator for the CREDIT_CARD pack's real evidence
doc types (SALARY_SLIP, ITR_V_ACKNOWLEDGEMENT, UTILITY_BILL_ELECTRICITY),
sourced from `app/packs/manifests/credit_card.yaml` evidence_mappings.

`SALARY_SLIP` is the same doc_type NAME as Lending's - a real,
unavoidable overlap (both journeys genuinely accept an actual salary
slip as income evidence), NOT a copy: this file generates its own
independent synthetic content (different template designs, different
randomized values, its own dataset/model artifacts under
`data/docai/credit_card/` and `credit_card_classifier.joblib`) - nothing
is shared except the document TYPE concept itself and, at extraction
time, the existing generic `extract_monthly_income()` label vocabulary
("Net Pay"/"Net Salary"/etc.) - genuinely shared infrastructure (a real
salary slip's label wording isn't journey-specific), not Lending business
logic. `ITR_V_ACKNOWLEDGEMENT` and `UTILITY_BILL_ELECTRICITY` are
entirely new document types with no equivalent in Lending/Insurance/KYC.

Run: `uv run python -m app.docai.dataset.generate_credit_card`
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

DATASET_ROOT = Path(__file__).resolve().parents[3] / "data" / "docai" / "credit_card"
SEED = 20260917  # distinct from every other journey's seed

ELECTRICITY_BOARDS = [
    "Metro Power Distribution Ltd",
    "State Electricity Board",
    "City Grid Utilities",
    "Regional Power Supply Co",
]
COMPANY_SUFFIXES = ["Pvt Ltd", "Technologies Pvt Ltd", "Solutions India Pvt Ltd", "Industries Ltd"]


def _fmt_amount(amount: int) -> str:
    s = str(amount)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        return ",".join(groups) + "," + tail
    return s


def _rand_pan(rng: random.Random) -> str:
    # Real Indian PAN format: 5 letters + 4 digits + 1 letter.
    letters1 = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(5))
    digits = "".join(str(rng.randint(0, 9)) for _ in range(4))
    letter2 = rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"{letters1}{digits}{letter2}"


def _make_fields(rng: random.Random, fake: Faker, doc_type: str) -> dict:
    net = rng.randrange(28000, 260000, 1000)
    return {
        "name": fake.name(),
        "employer_name": fake.company().replace(",", "") + " " + rng.choice(COMPANY_SUFFIXES),
        "net_amt": net,
        "pay_period": fake.date(pattern="%b %Y"),
        "pan": _rand_pan(rng),
        "assessment_year": f"{rng.randint(2018, 2024)}-{rng.randint(2019, 2025)}",
        "total_income": rng.randrange(300000, 3000000, 10000),
        "board": rng.choice(ELECTRICITY_BOARDS),
        "consumer_no": f"{rng.randint(100000000, 999999999)}",
        "bill_date": fake.date(pattern="%d/%m/%Y"),
        "bill_amount": rng.randrange(500, 8000, 100),
        "address": f"{fake.street_address()}, {fake.city()}",
    }


def _draw_salary_slip(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "salary_table":
        c.setFont("Helvetica-Bold", 13)
        c.drawString(20 * mm, h - 20 * mm, f["employer_name"])
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 27 * mm, "Payslip for " + f["pay_period"])
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 38 * mm, f"Employee Name: {f['name']}")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 48 * mm, "Basic Pay")
        c.drawRightString(120 * mm, h - 48 * mm, f"Rs. {_fmt_amount(int(f['net_amt'] * 0.6))}")
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 58 * mm, "Net Pay")
        c.drawRightString(120 * mm, h - 58 * mm, f"Rs. {_fmt_amount(f['net_amt'])}")
    elif template == "salary_compact":
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 18 * mm, f"{f['employer_name']} - Salary Slip")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Name: {f['name']} | Pay Period: {f['pay_period']}")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 35 * mm, f"Net Salary Credited: Rs. {_fmt_amount(f['net_amt'])}")
    else:  # salary_letterhead_unseen
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, "PAYROLL DEPARTMENT")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 24 * mm, f["employer_name"])
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 38 * mm, f"This confirms the salary disbursement for {f['name']}")
        c.drawString(20 * mm, h - 44 * mm, f"for the period {f['pay_period']}.")
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 55 * mm, f"Take Home: Rs. {_fmt_amount(f['net_amt'])}")


def _draw_itr(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "itr_formal":
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(w / 2, h - 20 * mm, "INCOME TAX RETURN - ACKNOWLEDGEMENT")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 33 * mm, f"PAN: {f['pan']}")
        c.drawString(20 * mm, h - 40 * mm, f"Name: {f['name']}")
        c.drawString(20 * mm, h - 47 * mm, f"Assessment Year: {f['assessment_year']}")
        c.drawString(20 * mm, h - 54 * mm, f"Total Income: Rs. {_fmt_amount(f['total_income'])}")
        c.drawString(20 * mm, h - 61 * mm, f"Date of Filing: {f['bill_date']}")
    elif template == "itr_compact":
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, "ITR-V Acknowledgement")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Name: {f['name']}  PAN {f['pan']}")
        c.drawString(
            20 * mm,
            h - 35 * mm,
            f"AY {f['assessment_year']}  Income Rs. {_fmt_amount(f['total_income'])}",
        )
    else:  # itr_letterhead_unseen
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, "INCOME TAX DEPARTMENT")
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 24 * mm, "Centralized Processing Centre")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 38 * mm, f"This acknowledges the return filed by {f['name']},")
        c.drawString(20 * mm, h - 44 * mm, f"holder of Permanent Account Number {f['pan']}.")
        c.drawString(20 * mm, h - 51 * mm, f"Assessment Year: {f['assessment_year']}")
        c.drawString(20 * mm, h - 58 * mm, f"Declared Income: Rs. {_fmt_amount(f['total_income'])}")


def _draw_utility_bill(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "utility_standard":
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, h - 20 * mm, f["board"])
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(w / 2, h - 30 * mm, "ELECTRICITY BILL")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 42 * mm, f"Consumer Name: {f['name']}")
        c.drawString(20 * mm, h - 49 * mm, f"Consumer No: {f['consumer_no']}")
        c.drawString(20 * mm, h - 56 * mm, f"Address: {f['address']}")
        c.drawString(20 * mm, h - 63 * mm, f"Bill Date: {f['bill_date']}")
        c.drawString(20 * mm, h - 70 * mm, f"Amount Due: Rs. {f['bill_amount']}")
    elif template == "utility_compact":
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, f"{f['board']} - Bill Summary")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Name: {f['name']}")
        c.drawString(20 * mm, h - 35 * mm, f"Consumer No {f['consumer_no']}  Date {f['bill_date']}")
        c.drawString(20 * mm, h - 42 * mm, f"Address: {f['address']}")
    else:  # utility_letterhead_unseen
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, h - 18 * mm, "OFFICE OF THE ELECTRICITY SUPPLY BOARD")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 32 * mm, f"Billed to: {f['name']}")
        c.drawString(20 * mm, h - 39 * mm, f"Service Address: {f['address']}")
        c.drawString(20 * mm, h - 46 * mm, f"Consumer Account: {f['consumer_no']}")
        c.drawString(20 * mm, h - 53 * mm, f"Billing Date: {f['bill_date']}")


def _draw_other(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 20 * mm, "QuickBuy Electronics - Invoice")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 30 * mm, f"Invoice No: INV-{f['consumer_no'][-5:]}")
    c.drawString(20 * mm, h - 36 * mm, f"Customer: {f['name']}")
    y = h - 50 * mm
    for item, amt in [("Headphones", 1800), ("Charger", 600), ("Total", 2400)]:
        c.drawString(20 * mm, y, item)
        c.drawRightString(100 * mm, y, str(amt))
        y -= 7 * mm


TEMPLATES: dict[str, list[str]] = {
    "SALARY_SLIP": ["salary_table", "salary_compact", "salary_letterhead_unseen"],
    "ITR_V_ACKNOWLEDGEMENT": ["itr_formal", "itr_compact", "itr_letterhead_unseen"],
    "UTILITY_BILL_ELECTRICITY": [
        "utility_standard",
        "utility_compact",
        "utility_letterhead_unseen",
    ],
    "OTHER": ["receipt"],
}
UNSEEN_TEMPLATE: dict[str, str] = {
    "SALARY_SLIP": "salary_letterhead_unseen",
    "ITR_V_ACKNOWLEDGEMENT": "itr_letterhead_unseen",
    "UTILITY_BILL_ELECTRICITY": "utility_letterhead_unseen",
}

DRAW_FN = {
    "SALARY_SLIP": _draw_salary_slip,
    "ITR_V_ACKNOWLEDGEMENT": _draw_itr,
    "UTILITY_BILL_ELECTRICITY": _draw_utility_bill,
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
        if doc_type == "SALARY_SLIP":
            gt_fields["document_date"] = fields["pay_period"]
            gt_fields["monthly_income"] = fields["net_amt"]
        elif doc_type == "ITR_V_ACKNOWLEDGEMENT":
            gt_fields["identifier"] = fields["pan"]
        elif doc_type == "UTILITY_BILL_ELECTRICITY":
            gt_fields["document_date"] = fields["bill_date"]

        label = DocumentLabel(
            sample_id=sample_id,
            journey_type="CREDIT_CARD",
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

    for doc_type in ["SALARY_SLIP", "ITR_V_ACKNOWLEDGEMENT", "UTILITY_BILL_ELECTRICITY"]:
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
                journey_type="CREDIT_CARD",
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
    print((root / "dataset_manifest.json").read_text())
