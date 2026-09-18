"""Synthetic document generator for the INSURANCE pack's real evidence
doc types (MEDICAL_DISCHARGE_SUMMARY, HEALTH_CHECKUP_REPORT,
PREVIOUS_POLICY_COPY), sourced from `app/packs/manifests/insurance.yaml`
evidence_mappings - not invented, and NOT copied from Lending's doc types,
fields, or content in any way (no salary/bank/employer content anywhere
in this file).

Structural pattern (templates/splits/degradation/DocumentLabel schema,
`_degrade` helper) is reused from `dataset/generate.py` since that
machinery is genuinely journey-agnostic; every piece of actual document
CONTENT below is Insurance-specific and independently written.

All 3 Insurance evidence doc types map to the SAME BOOLEAN target field
(`ped_declaration_submitted`) per the manifest's evidence_mappings - this
is structurally different from Lending (which had 2 money/text VALUE
fields to extract). Ground-truth "fields" for each sample therefore
record classification-relevant facts (name, document_date) for
cross-document consistency, not a money/text value to extract - there is
none, and inventing one would misrepresent this manifest's actual shape.

Run: `uv run python -m app.docai.dataset.generate_insurance`
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

DATASET_ROOT = Path(__file__).resolve().parents[3] / "data" / "docai" / "insurance"
SEED = 20260915  # distinct from Lending's SEED - independent dataset, not a reused sequence

HOSPITALS = [
    "Sunrise Multispeciality Hospital",
    "City Care Medical Centre",
    "St. Xavier's Hospital",
    "Lotus Diagnostics & Hospital",
]
LABS = [
    "Apex Diagnostics Lab",
    "MedCheck Health Labs",
    "Wellness Path Diagnostics",
    "Vitality Health Screening Centre",
]
INSURERS = [
    "Bharat General Insurance Co",
    "SafeLife Health Insurance",
    "Trustworthy Assurance Ltd",
    "Nationwide Mediclaim Co",
]

ACUTE_DIAGNOSES = [
    "Acute Appendicitis - fully resolved, no recurrence",
    "Fracture, Left Radius - healed, no ongoing treatment",
    "Acute Gastroenteritis - resolved, discharged stable",
]
CHRONIC_DIAGNOSES = [
    "Type 2 Diabetes Mellitus - ongoing management required",
    "Hypertension - continuing medication and monitoring",
    "Chronic Kidney Disease Stage 2 - long-term follow-up",
]


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


def _make_fields(rng: random.Random, fake: Faker, doc_type: str) -> dict:
    name = fake.name()
    is_chronic = rng.random() < 0.5
    diagnosis = rng.choice(CHRONIC_DIAGNOSES if is_chronic else ACUTE_DIAGNOSES)
    return {
        "name": name,
        "age": rng.randint(22, 68),
        "hospital": rng.choice(HOSPITALS),
        "lab": rng.choice(LABS),
        "insurer": rng.choice(INSURERS),
        "diagnosis": diagnosis,
        "condition_type": "CHRONIC_MAINTENANCE" if is_chronic else "RESOLVED_ACUTE",
        "admission_date": fake.date(pattern="%d/%m/%Y"),
        "discharge_date": fake.date(pattern="%d/%m/%Y"),
        "report_date": fake.date(pattern="%d/%m/%Y"),
        "policy_number": f"POL{rng.randint(100000, 999999)}",
        "sum_insured": rng.randrange(300000, 5000000, 50000),
        "policy_start": fake.date(pattern="%d/%m/%Y"),
        "policy_end": fake.date(pattern="%d/%m/%Y"),
        "bp": f"{rng.randint(110, 150)}/{rng.randint(70, 95)}",
        "sugar": rng.randint(80, 180),
        "cholesterol": rng.randint(150, 260),
    }


def _draw_discharge_summary(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "discharge_formal":
        c.setFont("Helvetica-Bold", 14)
        c.drawString(20 * mm, h - 20 * mm, f["hospital"])
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(w / 2, h - 32 * mm, "DISCHARGE SUMMARY")
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, h - 45 * mm, f"Patient Name: {f['name']}")
        c.drawString(20 * mm, h - 52 * mm, f"Age: {f['age']}")
        c.drawString(20 * mm, h - 59 * mm, f"Date of Admission: {f['admission_date']}")
        c.drawString(20 * mm, h - 66 * mm, f"Date of Discharge: {f['discharge_date']}")
        c.drawString(20 * mm, h - 78 * mm, f"Diagnosis: {f['diagnosis']}")
    elif template == "discharge_compact":
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, h - 18 * mm, f"{f['hospital']} - Discharge Record")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Patient: {f['name']} ({f['age']} yrs)")
        c.drawString(
            20 * mm,
            h - 35 * mm,
            f"Admitted: {f['admission_date']}  Discharged: {f['discharge_date']}",
        )
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 48 * mm, "Clinical Summary")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 56 * mm, f["diagnosis"])
    else:  # discharge_letterhead_unseen
        c.setFont("Helvetica-Bold", 13)
        c.drawString(20 * mm, h - 22 * mm, f["hospital"].upper())
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 28 * mm, "Medical Records Department")
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 42 * mm, "CERTIFICATE OF DISCHARGE")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 55 * mm, f"This is to certify that {f['name']}, aged {f['age']},")
        c.drawString(
            20 * mm,
            h - 61 * mm,
            f"was admitted on {f['admission_date']} and discharged on {f['discharge_date']}.",
        )
        c.drawString(20 * mm, h - 72 * mm, f"Condition: {f['diagnosis']}")


def _draw_health_checkup(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "checkup_table":
        c.setFont("Helvetica-Bold", 13)
        c.drawString(20 * mm, h - 20 * mm, f["lab"])
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(w / 2, h - 30 * mm, "ANNUAL HEALTH CHECKUP REPORT")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 42 * mm, f"Name: {f['name']}  Age: {f['age']}")
        c.drawString(20 * mm, h - 49 * mm, f"Report Date: {f['report_date']}")
        y = h - 62 * mm
        for label, val in [
            ("Blood Pressure", f["bp"]),
            ("Blood Sugar (mg/dL)", f["sugar"]),
            ("Cholesterol (mg/dL)", f["cholesterol"]),
        ]:
            c.drawString(25 * mm, y, f"{label}: {val}")
            y -= 7 * mm
    elif template == "checkup_summary":
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, h - 18 * mm, f"{f['lab']} - Health Screening Summary")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Patient Name: {f['name']}")
        c.drawString(20 * mm, h - 35 * mm, f"Date of Report: {f['report_date']}")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 48 * mm, "Vitals")
        c.setFont("Helvetica", 9)
        c.drawString(
            20 * mm,
            h - 56 * mm,
            f"BP {f['bp']}, Sugar {f['sugar']}, Cholesterol {f['cholesterol']}",
        )
    else:  # checkup_letterhead_unseen
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, h - 20 * mm, f["lab"].upper())
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 26 * mm, "Preventive Health Division")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 40 * mm, "COMPREHENSIVE WELLNESS REPORT")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 52 * mm, f"Subject: {f['name']}, Age {f['age']}")
        c.drawString(20 * mm, h - 58 * mm, f"Screening Date: {f['report_date']}")
        c.drawString(
            20 * mm, h - 68 * mm, f"BP {f['bp']} | Glucose {f['sugar']} | Lipids {f['cholesterol']}"
        )


def _draw_policy_copy(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "policy_schedule":
        c.setFont("Helvetica-Bold", 13)
        c.drawString(20 * mm, h - 20 * mm, f["insurer"])
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(w / 2, h - 30 * mm, "POLICY SCHEDULE")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 42 * mm, f"Policyholder Name: {f['name']}")
        c.drawString(20 * mm, h - 49 * mm, f"Policy Number: {f['policy_number']}")
        c.drawString(20 * mm, h - 56 * mm, f"Sum Insured: Rs. {_fmt_amount(f['sum_insured'])}")
        c.drawString(
            20 * mm, h - 63 * mm, f"Policy Period: {f['policy_start']} to {f['policy_end']}"
        )
    elif template == "policy_certificate":
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, h - 18 * mm, f"{f['insurer']} - Certificate of Insurance")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Insured: {f['name']}")
        c.drawString(
            20 * mm,
            h - 35 * mm,
            f"Policy No: {f['policy_number']}  Cover: Rs. {_fmt_amount(f['sum_insured'])}",
        )
        c.drawString(20 * mm, h - 42 * mm, f"Valid: {f['policy_start']} - {f['policy_end']}")
    else:  # policy_letterhead_unseen
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, h - 20 * mm, f["insurer"].upper())
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 26 * mm, "Health Insurance Division")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 40 * mm, "PREVIOUS POLICY DOCUMENT")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 52 * mm, f"Name of Policyholder: {f['name']}")
        c.drawString(20 * mm, h - 58 * mm, f"Ref: {f['policy_number']}")
        c.drawString(20 * mm, h - 64 * mm, f"Assured Sum: Rs. {_fmt_amount(f['sum_insured'])}")
        c.drawString(20 * mm, h - 70 * mm, f"Policy Date: {f['policy_start']}")


def _draw_other(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 20 * mm, "GreenMart Supermarket - Tax Invoice")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 30 * mm, f"Bill No: BILL-{f['policy_number'][-5:]}")
    c.drawString(20 * mm, h - 36 * mm, f"Customer: {f['name']}")
    y = h - 50 * mm
    for item, amt in [("Groceries", 980), ("Household", 540), ("Total", 1520)]:
        c.drawString(20 * mm, y, item)
        c.drawRightString(100 * mm, y, str(amt))
        y -= 7 * mm


TEMPLATES: dict[str, list[str]] = {
    "MEDICAL_DISCHARGE_SUMMARY": [
        "discharge_formal",
        "discharge_compact",
        "discharge_letterhead_unseen",
    ],
    "HEALTH_CHECKUP_REPORT": ["checkup_table", "checkup_summary", "checkup_letterhead_unseen"],
    "PREVIOUS_POLICY_COPY": ["policy_schedule", "policy_certificate", "policy_letterhead_unseen"],
    "OTHER": ["receipt"],
}
UNSEEN_TEMPLATE: dict[str, str] = {
    "MEDICAL_DISCHARGE_SUMMARY": "discharge_letterhead_unseen",
    "HEALTH_CHECKUP_REPORT": "checkup_letterhead_unseen",
    "PREVIOUS_POLICY_COPY": "policy_letterhead_unseen",
}

DRAW_FN = {
    "MEDICAL_DISCHARGE_SUMMARY": _draw_discharge_summary,
    "HEALTH_CHECKUP_REPORT": _draw_health_checkup,
    "PREVIOUS_POLICY_COPY": _draw_policy_copy,
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
        if doc_type == "MEDICAL_DISCHARGE_SUMMARY":
            gt_fields["document_date"] = fields["discharge_date"]
            gt_fields["condition_type"] = fields["condition_type"]
        elif doc_type == "HEALTH_CHECKUP_REPORT":
            gt_fields["document_date"] = fields["report_date"]
        elif doc_type == "PREVIOUS_POLICY_COPY":
            gt_fields["document_date"] = fields["policy_start"]
            gt_fields["sum_insured"] = fields["sum_insured"]

        label = DocumentLabel(
            sample_id=sample_id,
            journey_type="INSURANCE",
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

    for doc_type in ["MEDICAL_DISCHARGE_SUMMARY", "HEALTH_CHECKUP_REPORT", "PREVIOUS_POLICY_COPY"]:
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
                journey_type="INSURANCE",
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
