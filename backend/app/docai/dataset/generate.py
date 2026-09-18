"""Synthetic document generator for the LENDING pack's 4 real evidence
doc types (SALARY_SLIP, BANK_STATEMENT, OFFICE_ID_CARD, OFFER_LETTER),
sourced from `app/packs/manifests/lending.yaml` evidence_mappings - not
invented.

Why synthetic: no real Indian salary slips/bank statements/ID cards/offer
letters exist anywhere in this repository (confirmed by repo-wide search),
and obtaining genuine ones would be a privacy/licensing problem. Every
document here is fabricated content (fake names via Faker, fake amounts,
fake company names) rendered onto deliberately varied templates. This is
disclosed as a limitation in the evaluation report: measured accuracy is
against synthetic layouts, not a guarantee of real-world scan performance.

For each doc_type there are 4 distinct visual templates (different issuer
letterheads, field labels/wording, and layouts). One template per doc_type
is reserved exclusively for the `unseen_template` split and never appears
in train/val/test - this is what the mandatory unseen-template evaluation
(mission Phase 4/18) actually measures.

Each sample is rendered twice:
  - a native-text PDF (reportlab) -> exercises the PyMuPDF text-layer path
  - a degraded JPEG rasterization of that same PDF (rotation, gaussian
    noise, blur, JPEG re-compression) -> exercises the real Tesseract OCR
    path and is the primary artifact used for classifier/extractor
    training and evaluation, since that is the harder and more realistic
    case (a phone photo / scan), not a lucky vector-text shortcut.

A 5th synthetic class, doc_type="OTHER", is a deliberately unrelated
document (a grocery receipt / generic letter) used to test wrong-document
and out-of-set detection - never treated as a valid evidence_mappings
doc_type by the pipeline, only as a classifier negative.

A small set of doc_type="UNREADABLE" samples (blank page / heavy noise)
tests the "cannot reliably process" safe path.

Run: `uv run python -m app.docai.dataset.generate`
"""

from __future__ import annotations

import io
import json
import random
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from faker import Faker
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.docai.dataset.schema import DocumentLabel

DATASET_ROOT = Path(__file__).resolve().parents[3] / "data" / "docai" / "lending"
SEED = 20260914

INDIAN_BANKS = [
    "HDFC Bank",
    "ICICI Bank",
    "State Bank of India",
    "Axis Bank",
    "Kotak Mahindra Bank",
]
COMPANY_SUFFIXES = ["Pvt Ltd", "Technologies Pvt Ltd", "Solutions India Pvt Ltd", "Industries Ltd"]


def _fmt_indian_amount(amount: int, style: str) -> str:
    """Formats an integer amount using one of several real-world Indian
    currency notations (mission Phase 11)."""
    # Indian digit grouping: last 3 digits, then groups of 2.
    s = str(amount)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        grouped = ",".join(groups) + "," + tail
    else:
        grouped = s
    if style == "symbol":
        return f"₹{grouped}"
    if style == "rs_dot":
        return f"Rs. {grouped}"
    if style == "inr":
        return f"INR {grouped}"
    return grouped


def _degrade(pil_img: Image.Image, rng: random.Random) -> tuple[Image.Image, dict]:
    """Applies randomized, realistic scan/photo degradation. Returns the
    degraded image plus a record of exactly what was applied (for error
    analysis, per mission Phase 19)."""
    rotation_deg = rng.uniform(-3.5, 3.5)
    blur_radius = rng.choice([0, 0, 0.4, 0.8])
    noise_sigma = rng.choice([0, 3, 6])
    jpeg_quality = rng.choice([55, 70, 85])

    img = pil_img.convert("RGB").rotate(rotation_deg, expand=True, fillcolor=(255, 255, 255))
    if blur_radius:
        img = img.filter(ImageFilter.GaussianBlur(blur_radius))
    if noise_sigma:
        import numpy as np

        arr = np.array(img).astype(np.int16)
        noise = np.random.default_rng(rng.randint(0, 1_000_000)).normal(0, noise_sigma, arr.shape)
        arr = np.clip(arr + noise, 0, 255).astype("uint8")
        img = Image.fromarray(arr)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality)
    buf.seek(0)
    return Image.open(buf), {
        "rotation_deg": round(rotation_deg, 2),
        "blur_radius": blur_radius,
        "noise_sigma": noise_sigma,
        "jpeg_quality": jpeg_quality,
    }


@dataclass
class Sample:
    doc_type: str
    template_id: str
    fields: dict
    draw_fn_name: str


def _draw_salary_slip(c: canvas.Canvas, fields: dict, template: str) -> None:
    w, h = A4
    if template == "salary_table":
        c.setFont("Helvetica-Bold", 14)
        c.drawString(20 * mm, h - 25 * mm, f"{fields['employer_name']}")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 32 * mm, "Payslip for the month of " + fields["pay_period"])
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 45 * mm, f"Employee Name: {fields['name']}")
        c.drawString(20 * mm, h - 52 * mm, f"Employee ID: {fields['emp_id']}")
        rows = [
            ("Basic Pay", fields["basic_amt"]),
            ("HRA", fields["hra_amt"]),
            ("Gross Earnings", fields["gross_amt"]),
            ("Deductions", fields["deductions_amt"]),
        ]
        y = h - 70 * mm
        c.setFont("Helvetica", 10)
        for label, amt in rows:
            c.drawString(25 * mm, y, label)
            c.drawRightString(120 * mm, y, fields["_fmt"](amt))
            y -= 7 * mm
        c.setFont("Helvetica-Bold", 12)
        c.drawString(25 * mm, y - 5 * mm, "Net Pay")
        c.drawRightString(120 * mm, y - 5 * mm, fields["_fmt"](fields["net_amt"]))
    elif template == "salary_two_col":
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(w / 2, h - 22 * mm, f"{fields['employer_name']} - Salary Statement")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 35 * mm, f"Name: {fields['name']}")
        c.drawString(120 * mm, h - 35 * mm, f"Month: {fields['pay_period']}")
        c.drawString(20 * mm, h - 42 * mm, f"Designation: {fields['designation']}")
        y = h - 60 * mm
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, y, f"Basic: {fields['_fmt'](fields['basic_amt'])}")
        c.drawString(20 * mm, y - 7 * mm, f"Allowances: {fields['_fmt'](fields['hra_amt'])}")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(
            20 * mm, y - 20 * mm, f"Net Salary Credited: {fields['_fmt'](fields['net_amt'])}"
        )
    else:  # salary_header (3rd non-unseen) / offer_unseen_layout (reserved)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(20 * mm, h - 20 * mm, "MONTHLY PAY ADVICE")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, fields["employer_name"])
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, h - 45 * mm, f"Employee: {fields['name']} ({fields['emp_id']})")
        c.drawString(20 * mm, h - 52 * mm, f"Period: {fields['pay_period']}")
        c.setFont("Helvetica-Bold", 12)
        label = "Take Home" if template == "salary_takehome" else "Net Amount Payable"
        c.drawString(20 * mm, h - 70 * mm, f"{label}: {fields['_fmt'](fields['net_amt'])}")


def _draw_bank_statement(c: canvas.Canvas, fields: dict, template: str) -> None:
    w, h = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 20 * mm, f"{fields['bank_name']} - Account Statement")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 28 * mm, f"Account Holder: {fields['name']}")
    c.drawString(
        20 * mm, h - 34 * mm, f"Account No: {fields['account_no']}  IFSC: {fields['ifsc']}"
    )
    c.setFont("Helvetica-Bold", 10)
    label_row = {
        "bank_hdfc": "Date        Description                        Credit",
        "bank_icici": "Txn Date    Narration                          Amount(Cr)",
        "bank_sbi": "Value Date  Particulars                         Deposit",
        "bank_axis_unseen": "Posted On   Transaction Details                Inflow",
    }[template]
    y = h - 48 * mm
    c.drawString(20 * mm, y, label_row)
    c.setFont("Helvetica", 9)
    y -= 7 * mm
    salary_label = {
        "bank_hdfc": "SALARY CREDIT " + fields["employer_name"].upper(),
        "bank_icici": "NEFT-SALARY-" + fields["employer_name"].upper(),
        "bank_sbi": "BY SALARY " + fields["employer_name"].upper(),
        "bank_axis_unseen": "SAL/" + fields["employer_name"].upper(),
    }[template]
    for desc, amt in [
        ("OPENING BALANCE", None),
        (salary_label, fields["net_amt"]),
        ("UTILITY BILL PAYMENT", -fields["misc_amt"]),
    ]:
        c.drawString(20 * mm, y, fields["pay_period"] + "  " + desc[:34])
        if amt is not None:
            c.drawRightString(160 * mm, y, fields["_fmt"](abs(amt)))
        y -= 6 * mm


def _draw_office_id(c: canvas.Canvas, fields: dict, template: str) -> None:
    w, h = A4
    c.setFillColorRGB(0.93, 0.95, 0.98)
    c.rect(15 * mm, h - 70 * mm, 90 * mm, 50 * mm, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    if template in ("id_horizontal", "id_vertical"):
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, h - 25 * mm, fields["employer_name"])
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 31 * mm, "EMPLOYEE IDENTITY CARD")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 45 * mm, fields["name"])
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 52 * mm, f"Emp ID: {fields['emp_id']}")
        c.drawString(20 * mm, h - 58 * mm, f"Designation: {fields['designation']}")
    else:  # id_qr_unseen
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 25 * mm, "STAFF ID")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 35 * mm, fields["name"])
        c.drawString(20 * mm, h - 41 * mm, f"ID No. {fields['emp_id']}")
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 60 * mm, fields["employer_name"])


def _draw_offer_letter(c: canvas.Canvas, fields: dict, template: str) -> None:
    w, h = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 20 * mm, fields["employer_name"])
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 27 * mm, fields["employer_address"])
    c.setFont("Helvetica-Bold", 12)
    title = {
        "offer_formal": "OFFER OF EMPLOYMENT",
        "offer_block": "Employment Offer",
        "offer_letterhead_unseen": "EMPLOYMENT OFFER LETTER",
    }[template]
    c.drawCentredString(w / 2, h - 45 * mm, title)
    c.setFont("Helvetica", 10)
    text = c.beginText(20 * mm, h - 60 * mm)
    text.setLeading(14)
    lines = [
        f"Date: {fields['pay_period']}",
        "",
        f"Dear {fields['name']},",
        "",
        f"We are pleased to offer you the position of {fields['designation']} at",
        f"{fields['employer_name']}. Your annual compensation for this role is",
        f"{fields['_fmt'](fields['net_amt'] * 12)}, payable in accordance with company policy.",
        "",
        "We look forward to welcoming you to the team.",
    ]
    for line in lines:
        text.textLine(line)
    c.drawText(text)


def _draw_other(c: canvas.Canvas, fields: dict, template: str) -> None:
    w, h = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 20 * mm, "FreshMart Retail - Tax Invoice")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 30 * mm, f"Invoice No: INV-{fields['emp_id']}")
    c.drawString(20 * mm, h - 36 * mm, f"Customer: {fields['name']}")
    y = h - 50 * mm
    for item, amt in [("Groceries", 1240), ("Household Items", 860), ("Total", 2100)]:
        c.drawString(20 * mm, y, item)
        c.drawRightString(100 * mm, y, fields["_fmt"](amt))
        y -= 7 * mm


TEMPLATES: dict[str, list[str]] = {
    "SALARY_SLIP": ["salary_table", "salary_two_col", "salary_header", "salary_takehome"],
    "BANK_STATEMENT": ["bank_hdfc", "bank_icici", "bank_sbi", "bank_axis_unseen"],
    "OFFICE_ID_CARD": ["id_horizontal", "id_vertical", "id_qr_unseen"],
    "OFFER_LETTER": ["offer_formal", "offer_block", "offer_letterhead_unseen"],
    "OTHER": ["receipt"],
}
# Last template listed per doc_type is reserved for unseen_template ONLY.
UNSEEN_TEMPLATE: dict[str, str] = {
    "SALARY_SLIP": "salary_takehome",
    "BANK_STATEMENT": "bank_axis_unseen",
    "OFFICE_ID_CARD": "id_qr_unseen",
    "OFFER_LETTER": "offer_letterhead_unseen",
}

DRAW_FN = {
    "SALARY_SLIP": _draw_salary_slip,
    "BANK_STATEMENT": _draw_bank_statement,
    "OFFICE_ID_CARD": _draw_office_id,
    "OFFER_LETTER": _draw_offer_letter,
    "OTHER": _draw_other,
}


def _make_fields(rng: random.Random, fake: Faker, doc_type: str, amount_style: str) -> dict:
    name = fake.name()
    company = fake.company().replace(",", "") + " " + rng.choice(COMPANY_SUFFIXES)
    net = rng.randrange(28000, 260000, 1000)
    basic = int(net * 0.6)
    hra = int(net * 0.3)
    gross = basic + hra + int(net * 0.15)
    deductions = gross - net
    fields = {
        "name": name,
        "employer_name": company,
        "employer_address": fake.address().replace("\n", ", "),
        "designation": rng.choice(
            ["Software Engineer", "Analyst", "Manager", "Consultant", "Associate"]
        ),
        "emp_id": f"EMP{rng.randint(10000, 99999)}",
        "pay_period": fake.date(pattern="%b %Y"),
        "net_amt": net,
        "basic_amt": basic,
        "hra_amt": hra,
        "gross_amt": gross,
        "deductions_amt": deductions,
        "misc_amt": rng.randrange(500, 5000, 100),
        "bank_name": rng.choice(INDIAN_BANKS),
        "account_no": "".join(str(rng.randint(0, 9)) for _ in range(11)),
        "ifsc": rng.choice(["HDFC", "ICIC", "SBIN", "UTIB"])
        + "0"
        + "".join(str(rng.randint(0, 9)) for _ in range(6)),
        "_fmt": lambda amt, style=amount_style: _fmt_indian_amount(int(amt), style),
    }
    return fields


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

        gt_fields: dict = {}
        if doc_type == "SALARY_SLIP":
            gt_fields = {
                "monthly_income": fields["net_amt"],
                "name": fields["name"],
                "document_date": fields["pay_period"],
            }
        elif doc_type == "BANK_STATEMENT":
            gt_fields = {
                "monthly_income": fields["net_amt"],
                "name": fields["name"],
                "document_date": fields["pay_period"],
            }
        elif doc_type in ("OFFICE_ID_CARD", "OFFER_LETTER"):
            gt_fields = {"employer_name": fields["employer_name"], "name": fields["name"]}

        label = DocumentLabel(
            sample_id=sample_id,
            journey_type="LENDING",
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

    for doc_type in ["SALARY_SLIP", "BANK_STATEMENT", "OFFICE_ID_CARD", "OFFER_LETTER"]:
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
                    style = rng.choice(["symbol", "rs_dot", "inr", "plain"])
                    fields = _make_fields(rng, fake, doc_type, style)
                    _render_and_save(doc_type, template, fields, split)

        for _ in range(n_unseen):
            style = rng.choice(["symbol", "rs_dot", "inr", "plain"])
            fields = _make_fields(rng, fake, doc_type, style)
            _render_and_save(doc_type, unseen_tpl, fields, "unseen_template")

    # OTHER (wrong-document negative class) spread across splits
    for split, n in [
        ("train", n_other),
        ("val", max(3, n_other // 4)),
        ("test", max(3, n_other // 4)),
        ("unseen_template", max(3, n_other // 5)),
    ]:
        for _ in range(n):
            style = rng.choice(["symbol", "rs_dot", "inr", "plain"])
            fields = _make_fields(rng, fake, "OTHER", style)
            _render_and_save("OTHER", "receipt", fields, split)

    # UNREADABLE (blank / pure-noise) samples, test split only
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
                journey_type="LENDING",
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
