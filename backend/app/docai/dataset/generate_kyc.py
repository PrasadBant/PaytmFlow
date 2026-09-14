"""Synthetic document generator for the KYC pack's real evidence doc types
(PASSPORT_SCAN, VOTER_ID_CARD, DRIVING_LICENCE), sourced from
`app/packs/manifests/kyc.yaml` evidence_mappings - not invented, and NOT
copied from Lending's or Insurance's doc types, fields, or content.

Like Insurance, all 3 KYC evidence doc types map to the SAME BOOLEAN
target field (`ovd_document_uploaded`) - correct classification is the
fact, not a money/text value. Unlike Insurance, KYC documents carry a
real, well-defined GOVERNMENT IDENTIFIER per doc type (passport number,
EPIC/voter ID number, driving licence number), each with its own actual
Indian format - this is the genuinely new extraction surface this pack
requires (mission Step 5's "identifier formatting").

Run: `uv run python -m app.docai.dataset.generate_kyc`
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

DATASET_ROOT = Path(__file__).resolve().parents[3] / "data" / "docai" / "kyc"
SEED = 20260916  # distinct from Lending's and Insurance's seeds

INDIAN_CITIES = [
    "Mumbai",
    "Delhi",
    "Bengaluru",
    "Chennai",
    "Pune",
    "Ahmedabad",
    "Kolkata",
    "Hyderabad",
]
STATE_CODES = ["MH", "DL", "KA", "TN", "GJ", "WB", "UP", "RJ"]


def _rand_passport_no(rng: random.Random) -> str:
    letter = rng.choice("ABCDEFGHJKLMNPRTZ")  # real passport series letters (no I/O/Q/S/U/V/W/X/Y)
    digits = "".join(str(rng.randint(0, 9)) for _ in range(7))
    return f"{letter}{digits}"


def _rand_epic_no(rng: random.Random) -> str:
    letters = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(3))
    digits = "".join(str(rng.randint(0, 9)) for _ in range(7))
    return f"{letters}{digits}"


def _rand_dl_no(rng: random.Random) -> str:
    state = rng.choice(STATE_CODES)
    rto = f"{rng.randint(1, 99):02d}"
    year = rng.randint(1990, 2023)
    serial = f"{rng.randint(1, 9999999):07d}"
    return f"{state}{rto}{year}{serial}"


def _make_fields(rng: random.Random, fake: Faker, doc_type: str) -> dict:
    return {
        "name": fake.name(),
        "father_name": fake.name(),
        "dob": fake.date(pattern="%d/%m/%Y"),
        "issue_date": fake.date(pattern="%d/%m/%Y"),
        "expiry_date": fake.date(pattern="%d/%m/%Y"),
        "valid_till": fake.date(pattern="%d/%m/%Y"),
        "place_of_birth": rng.choice(INDIAN_CITIES),
        "address": f"{fake.street_address()}, {rng.choice(INDIAN_CITIES)}",
        "passport_no": _rand_passport_no(rng),
        "epic_no": _rand_epic_no(rng),
        "dl_no": _rand_dl_no(rng),
    }


def _draw_passport(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "passport_biopage":
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(w / 2, h - 18 * mm, "REPUBLIC OF INDIA - PASSPORT")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 32 * mm, f"Passport No: {f['passport_no']}")
        c.drawString(20 * mm, h - 39 * mm, f"Name: {f['name']}")
        c.drawString(20 * mm, h - 46 * mm, f"Date of Birth: {f['dob']}")
        c.drawString(20 * mm, h - 53 * mm, f"Place of Birth: {f['place_of_birth']}")
        c.drawString(20 * mm, h - 60 * mm, f"Date of Issue: {f['issue_date']}")
        c.drawString(20 * mm, h - 67 * mm, f"Date of Expiry: {f['expiry_date']}")
    elif template == "passport_compact":
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 18 * mm, "INDIAN PASSPORT")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Name: {f['name']} | DOB {f['dob']}")
        c.drawString(20 * mm, h - 35 * mm, f"No. {f['passport_no']}")
        c.drawString(
            20 * mm, h - 42 * mm, f"Issued: {f['issue_date']}  Expires: {f['expiry_date']}"
        )
    else:  # passport_letterhead_unseen
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, "PASSPORT SEVA KENDRA")
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 24 * mm, "Ministry of External Affairs")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 38 * mm, f"Holder: {f['name']}")
        c.drawString(20 * mm, h - 45 * mm, f"Passport Number: {f['passport_no']}")
        c.drawString(20 * mm, h - 52 * mm, f"Born: {f['dob']} at {f['place_of_birth']}")
        c.drawString(20 * mm, h - 59 * mm, f"Date of Issue: {f['issue_date']}")


def _draw_voter_id(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    c.setFillColorRGB(0.93, 0.97, 0.93)
    c.rect(15 * mm, h - 70 * mm, 90 * mm, 50 * mm, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    if template == "voter_standard":
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 22 * mm, "ELECTION COMMISSION OF INDIA")
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 28 * mm, "IDENTITY CARD")
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, h - 40 * mm, f"Elector's Name: {f['name']}")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 47 * mm, f"Father's Name: {f['father_name']}")
        c.drawString(20 * mm, h - 54 * mm, f"EPIC No: {f['epic_no']}")
        c.drawString(20 * mm, h - 61 * mm, f"Date of Birth: {f['dob']}")
    elif template == "voter_compact":
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 20 * mm, "Voter ID Card")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 30 * mm, f"Name: {f['name']}")
        c.drawString(20 * mm, h - 37 * mm, f"Card No: {f['epic_no']}")
        c.drawString(20 * mm, h - 44 * mm, f"DOB: {f['dob']}")
    else:  # voter_letterhead_unseen
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, h - 20 * mm, "OFFICE OF THE ELECTORAL REGISTRATION OFFICER")
        c.setFont("Helvetica", 9)
        c.drawString(
            20 * mm,
            h - 32 * mm,
            f"This is to certify that {f['name']}, son/daughter of {f['father_name']},",
        )
        c.drawString(20 * mm, h - 38 * mm, f"is a registered elector, EPIC No {f['epic_no']}.")
        c.drawString(20 * mm, h - 45 * mm, f"Date of Birth: {f['dob']}")


def _draw_driving_licence(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    if template == "dl_standard":
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, h - 20 * mm, "DRIVING LICENCE")
        c.setFont("Helvetica", 8)
        c.drawString(20 * mm, h - 26 * mm, "Union of India")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 38 * mm, f"DL No: {f['dl_no']}")
        c.drawString(20 * mm, h - 45 * mm, f"Name: {f['name']}")
        c.drawString(20 * mm, h - 52 * mm, f"Date of Birth: {f['dob']}")
        c.drawString(20 * mm, h - 59 * mm, f"Valid Till: {f['valid_till']}")
        c.drawString(20 * mm, h - 66 * mm, f"Address: {f['address']}")
    elif template == "dl_compact":
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, h - 18 * mm, "Regional Transport Office - DL")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 28 * mm, f"Name: {f['name']} ({f['dob']})")
        c.drawString(20 * mm, h - 35 * mm, f"Licence No {f['dl_no']}")
        c.drawString(20 * mm, h - 42 * mm, f"Valid Till {f['valid_till']}")
    else:  # dl_letterhead_unseen
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, h - 20 * mm, "STATE TRANSPORT AUTHORITY")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 32 * mm, f"Licence Holder: {f['name']}")
        c.drawString(20 * mm, h - 39 * mm, f"Licence Number: {f['dl_no']}")
        c.drawString(20 * mm, h - 46 * mm, f"Valid Till: {f['valid_till']}")
        c.drawString(20 * mm, h - 53 * mm, f"Residential Address: {f['address']}")


def _draw_other(c: canvas.Canvas, f: dict, template: str) -> None:
    w, h = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 20 * mm, "CityMart Store - Purchase Receipt")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 30 * mm, f"Receipt No: RCT-{f['epic_no'][-5:]}")
    c.drawString(20 * mm, h - 36 * mm, f"Customer: {f['name']}")
    y = h - 50 * mm
    for item, amt in [("Electronics", 2400), ("Accessories", 350), ("Total", 2750)]:
        c.drawString(20 * mm, y, item)
        c.drawRightString(100 * mm, y, str(amt))
        y -= 7 * mm


TEMPLATES: dict[str, list[str]] = {
    "PASSPORT_SCAN": ["passport_biopage", "passport_compact", "passport_letterhead_unseen"],
    "VOTER_ID_CARD": ["voter_standard", "voter_compact", "voter_letterhead_unseen"],
    "DRIVING_LICENCE": ["dl_standard", "dl_compact", "dl_letterhead_unseen"],
    "OTHER": ["receipt"],
}
UNSEEN_TEMPLATE: dict[str, str] = {
    "PASSPORT_SCAN": "passport_letterhead_unseen",
    "VOTER_ID_CARD": "voter_letterhead_unseen",
    "DRIVING_LICENCE": "dl_letterhead_unseen",
}

DRAW_FN = {
    "PASSPORT_SCAN": _draw_passport,
    "VOTER_ID_CARD": _draw_voter_id,
    "DRIVING_LICENCE": _draw_driving_licence,
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
        if doc_type == "PASSPORT_SCAN":
            gt_fields["document_date"] = fields["issue_date"]
            gt_fields["identifier"] = fields["passport_no"]
        elif doc_type == "VOTER_ID_CARD":
            gt_fields["document_date"] = fields["dob"]
            gt_fields["identifier"] = fields["epic_no"]
        elif doc_type == "DRIVING_LICENCE":
            gt_fields["document_date"] = fields["valid_till"]
            gt_fields["identifier"] = fields["dl_no"]

        label = DocumentLabel(
            sample_id=sample_id,
            journey_type="KYC",
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

    for doc_type in ["PASSPORT_SCAN", "VOTER_ID_CARD", "DRIVING_LICENCE"]:
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
                journey_type="KYC",
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
