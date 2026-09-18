"""Cross-document consistency, production-wired, real end-to-end tests
across all six journeys - real rendered PDFs, real OCR, real classifier,
real extraction, real `LocalMLProvider.reconcile_evidence`, comparing
against a REAL prior fact (not a hand-crafted "existing_fields" dict, as
the unit-level smoke checks used during development did) to prove the
whole `reconcile.py` -> evidence-persistence -> next-upload loop actually
works, not just the provider function in isolation.

Manifest reality, audited before writing any test here (see
docs/docai_cross_document_consistency_report.md §1/§3 for the full
per-journey table): a structural ambiguity_rule match (rule.field ==
the CURRENT evidence's mapping.target_field) exists for every journey
except Account Opening. The mechanism itself is fully generic - it
attaches to whichever ambiguity_rule structurally matches the target
field, with NO per-journey branching and no attempt to verify the
rule's own `question` TEXT is semantically about identity (the manifest
schema has no field tagging an ambiguity rule's topic, so a generic
mechanism cannot check this). For two journeys the match is also a
genuine semantic fit - Credit Card's `AMB_ADDRESS_MATCH` ("is the
utility bill in the name of your spouse...") and Investment's
`AMB_BANK_NAME_MISMATCH` ("confirm primary/secondary holder") - proven
below with matching AND conflicting cases. For three others (Lending's
`INCOME_MISMATCH`, Insurance's `AMB_PRE_EXISTING_ILLNESS`, KYC's
`AMB_EXPIRED_DOCUMENT`), the SAME mechanism still correctly detects and
surfaces a genuine name conflict (also proven below) - but the
ambiguity_id attached is a rule whose OWN static question is about a
different topic (income / illness / document expiry, not identity).
This is disclosed here as a real, known limitation: `EvidenceConflict`
carries the accurate dynamically-generated `message` shown immediately
after upload, but if the user later proceeds into a formal CLARIFICATION
resolution flow, the STATIC `question` text presented would reference
the wrong topic. NEEDS_REVIEW is still triggered correctly either way -
this is a UX-accuracy limitation, not a safety gap.
"""

import io
import random

import pymupdf
import pytest
from faker import Faker
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.ai.local_ml import LocalMLProvider
from app.docai.classifier import get_classifier
from app.docai.dataset.generate import _degrade
from app.docai.ocr import TESSERACT_AVAILABLE, extract_text
from app.packs.registry import pack_registry

pytestmark = [
    pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available."),
    pytest.mark.asyncio,
]


@pytest.fixture(autouse=True)
def load_manifests():
    pack_registry.load_all()


def _render_and_ocr(draw_fn, fields: dict, template: str, seed: int):
    rng = random.Random(seed)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_fn(c, fields, template)
    c.showPage()
    c.save()

    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=150)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
    degraded, _ = _degrade(pil_img, rng)
    img_buf = io.BytesIO()
    degraded.save(img_buf, format="JPEG", quality=85)

    ocr_result = extract_text(img_buf.getvalue(), "image/jpeg")
    ocr_meta = {
        "confidence": ocr_result.mean_word_confidence,
        "word_count": ocr_result.word_count,
        "engine": ocr_result.engine,
        "lines": [{"text": ln.text, "top": ln.top, "bottom": ln.bottom} for ln in ocr_result.lines],
    }
    return ocr_result.text, ocr_meta


def _render_clean(draw_fn, fields: dict, template: str):
    """Native-text PDF, no rasterization/degradation/Tesseract at all.

    Used only where a random seed through the full degraded-JPEG path was
    traced to occasionally hit an already-disclosed OCR artifact (a
    currency-symbol glyph misread as an extra leading digit) that
    manufactures a SECOND, spurious conflict unrelated to whatever the
    test is actually isolating (see TestLendingConsistency below). This
    is still a real code path (docai/ocr.py's native-PDF-text-layer
    branch, not a mock), just the other real path.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_fn(c, fields, template)
    c.showPage()
    c.save()
    ocr_result = extract_text(buf.getvalue(), "application/pdf")
    ocr_meta = {
        "confidence": ocr_result.mean_word_confidence,
        "word_count": ocr_result.word_count,
        "engine": ocr_result.engine,
        "lines": [{"text": ln.text, "top": ln.top, "bottom": ln.bottom} for ln in ocr_result.lines],
    }
    return ocr_result.text, ocr_meta


async def _reconcile(
    journey_type, doc_type, draw_fn, fields, template, seed, existing_fields, clean=False
):
    manifest = pack_registry.get_pack(journey_type)
    text, ocr_meta = (
        _render_clean(draw_fn, fields, template)
        if clean
        else _render_and_ocr(draw_fn, fields, template, seed)
    )
    provider = LocalMLProvider()
    return await provider.reconcile_evidence(
        doc_type=doc_type,
        extracted_text=text,
        manifest=manifest,
        existing_fields=existing_fields,
        ocr_meta=ocr_meta,
    )


pytestmark.append(
    pytest.mark.skipif(get_classifier("INVESTMENT") is None, reason="No trained classifier.")
)


class TestInvestmentConsistency:
    """The cleanest case: AMB_BANK_NAME_MISMATCH's field (bank_account_verified)
    is the shared target of CANCELLED_CHEQUE and BANK_STATEMENT_SUMMARY,
    and its question ("primary or secondary holder") is genuinely about a
    name-on-account scenario."""

    async def test_matching_name_across_alternate_evidence_no_conflict(self):
        from app.docai.dataset.generate_investment import (
            _draw_bank_statement,
            _draw_cancelled_cheque,
            _make_fields,
        )

        rng = random.Random(20260920)
        fake = Faker()
        Faker.seed(20260920)
        fields1 = _make_fields(rng, fake, "CANCELLED_CHEQUE")
        fields1["name"] = "Srija Uppuluri"
        result1 = await _reconcile(
            "INVESTMENT",
            "CANCELLED_CHEQUE",
            _draw_cancelled_cheque,
            fields1,
            "cheque_standard",
            6101,
            {},
        )
        assert result1.auxiliary_facts.get("name") == "Srija Uppuluri"

        fields2 = _make_fields(rng, fake, "BANK_STATEMENT_SUMMARY")
        fields2["name"] = "SRIJA UPPULURI"  # same person, different casing
        result2 = await _reconcile(
            "INVESTMENT",
            "BANK_STATEMENT_SUMMARY",
            _draw_bank_statement,
            fields2,
            "statement_standard",
            6102,
            {"name": result1.auxiliary_facts["name"]},
        )
        assert result2.conflicts == []
        assert result2.verified is True

    async def test_genuine_name_conflict_across_alternate_evidence_is_flagged(self):
        from app.docai.dataset.generate_investment import _draw_bank_statement, _make_fields

        rng = random.Random(20260921)
        fake = Faker()
        Faker.seed(20260921)
        fields = _make_fields(rng, fake, "BANK_STATEMENT_SUMMARY")
        fields["name"] = "Rahul Kumar"
        result = await _reconcile(
            "INVESTMENT",
            "BANK_STATEMENT_SUMMARY",
            _draw_bank_statement,
            fields,
            "statement_standard",
            6103,
            {"name": "Srija Uppuluri"},
        )
        assert len(result.conflicts) == 1
        assert result.conflicts[0].ambiguity_id == "AMB_BANK_NAME_MISMATCH"
        assert result.conflicts[0].field == "name"
        assert result.verified is False

    async def test_identifier_conflict_same_doc_type_no_matching_ambiguity_rule(self):
        # KRA_KYC_LETTER's target (kra_kyc_validated) has no ambiguity_rule
        # - the conflict is genuinely detected (proven via auxiliary_facts
        # differing) but correctly NOT surfaced, since there is nothing
        # safe to attach it to.
        from app.docai.dataset.generate_investment import _draw_kra_letter, _make_fields

        rng = random.Random(20260922)
        fake = Faker()
        Faker.seed(20260922)
        fields = _make_fields(rng, fake, "KRA_KYC_LETTER")
        result = await _reconcile(
            "INVESTMENT",
            "KRA_KYC_LETTER",
            _draw_kra_letter,
            fields,
            "kra_standard",
            6104,
            {"identifier::KRA_KYC_LETTER": "ZZZZZ0000Z"},
        )
        assert result.conflicts == []  # no ambiguity_rule for kra_kyc_validated
        assert result.auxiliary_facts.get("identifier::KRA_KYC_LETTER") != "ZZZZZ0000Z"

    async def test_missing_prior_fact_no_conflict(self):
        from app.docai.dataset.generate_investment import _draw_cancelled_cheque, _make_fields

        rng = random.Random(20260923)
        fake = Faker()
        Faker.seed(20260923)
        fields = _make_fields(rng, fake, "CANCELLED_CHEQUE")
        result = await _reconcile(
            "INVESTMENT",
            "CANCELLED_CHEQUE",
            _draw_cancelled_cheque,
            fields,
            "cheque_standard",
            6105,
            {},
        )
        assert result.conflicts == []


@pytest.mark.skipif(get_classifier("CREDIT_CARD") is None, reason="No trained classifier.")
class TestCreditCardConsistency:
    """AMB_ADDRESS_MATCH's field (current_address_verified) is
    UTILITY_BILL_ELECTRICITY's own target, and its question ("is the
    utility bill in the name of your spouse or family member") is
    genuinely about a name-on-document scenario."""

    async def test_name_conflict_between_salary_slip_and_utility_bill_is_flagged(self):
        from app.docai.dataset.generate_credit_card import _draw_utility_bill, _make_fields

        rng = random.Random(20260924)
        fake = Faker()
        Faker.seed(20260924)
        fields = _make_fields(rng, fake, "UTILITY_BILL_ELECTRICITY")
        fields["name"] = "Someone Else"
        result = await _reconcile(
            "CREDIT_CARD",
            "UTILITY_BILL_ELECTRICITY",
            _draw_utility_bill,
            fields,
            "utility_standard",
            6106,
            {"name": "Original Applicant"},
        )
        assert len(result.conflicts) == 1
        assert result.conflicts[0].ambiguity_id == "AMB_ADDRESS_MATCH"

    async def test_matching_name_no_conflict(self):
        from app.docai.dataset.generate_credit_card import _draw_utility_bill, _make_fields

        rng = random.Random(20260925)
        fake = Faker()
        Faker.seed(20260925)
        fields = _make_fields(rng, fake, "UTILITY_BILL_ELECTRICITY")
        fields["name"] = "Priya Sharma"
        result = await _reconcile(
            "CREDIT_CARD",
            "UTILITY_BILL_ELECTRICITY",
            _draw_utility_bill,
            fields,
            "utility_standard",
            6107,
            {"name": "priya sharma"},
        )
        assert result.conflicts == []


@pytest.mark.skipif(get_classifier("KYC") is None, reason="No trained classifier.")
class TestKycConsistency:
    """Structural match exists (AMB_EXPIRED_DOCUMENT's field,
    ovd_document_uploaded, is the shared target of all 3 KYC doc types),
    but its question is about document age, not identity. The generic
    mechanism still correctly detects AND surfaces the conflict (proven
    below) - the disclosed limitation is only that the ambiguity_id
    attached would show a document-expiry question if the user proceeds
    to a formal clarification, not that the conflict goes undetected."""

    async def test_name_conflict_is_detected_and_surfaced_with_a_topic_mismatched_rule(self):
        from app.docai.dataset.generate_kyc import _draw_voter_id, _make_fields

        rng = random.Random(20260926)
        fake = Faker()
        Faker.seed(20260926)
        fields = _make_fields(rng, fake, "VOTER_ID_CARD")
        fields["name"] = "Totally Different Name"
        result = await _reconcile(
            "KYC",
            "VOTER_ID_CARD",
            _draw_voter_id,
            fields,
            "voter_standard",
            6108,
            {"name": "Original Applicant Name"},
        )
        assert len(result.conflicts) == 1
        assert result.conflicts[0].ambiguity_id == "AMB_EXPIRED_DOCUMENT"
        assert result.conflicts[0].field == "name"
        assert "Totally Different Name" in result.conflicts[0].message
        assert result.verified is False
        assert result.auxiliary_facts.get("name") == "Totally Different Name"

    async def test_matching_name_no_conflict(self):
        from app.docai.dataset.generate_kyc import _draw_voter_id, _make_fields

        rng = random.Random(20260927)
        fake = Faker()
        Faker.seed(20260927)
        fields = _make_fields(rng, fake, "VOTER_ID_CARD")
        fields["name"] = "Aditya Rao"
        result = await _reconcile(
            "KYC",
            "VOTER_ID_CARD",
            _draw_voter_id,
            fields,
            "voter_standard",
            6109,
            {"name": "ADITYA RAO"},
        )
        assert result.conflicts == []


@pytest.mark.skipif(get_classifier("INSURANCE") is None, reason="No trained classifier.")
class TestInsuranceConsistency:
    """AMB_PRE_EXISTING_ILLNESS's field (ped_declaration_submitted) is the
    shared target of all 3 Insurance doc types - same disclosed
    topic-mismatch limitation as KYC above (the question is about
    undeclared conditions, not identity), but the conflict itself is
    still correctly detected and surfaced."""

    async def test_name_conflict_is_detected_and_surfaced_with_a_topic_mismatched_rule(self):
        from app.docai.dataset.generate_insurance import _draw_health_checkup, _make_fields

        rng = random.Random(20260928)
        fake = Faker()
        Faker.seed(20260928)
        fields = _make_fields(rng, fake, "HEALTH_CHECKUP_REPORT")
        # Deliberately avoid any word also present in the name-label
        # vocabulary (e.g. "Patient") - this template prints "Age" right
        # after the name on the same line, which the name capture already
        # bleeds into (a known, disclosed residual extraction gap - see
        # docs/docai_investment_report.md §8); picking fake names with no
        # shared tokens keeps this test about CONSISTENCY, not about that
        # separate, already-documented extraction limitation.
        fields["name"] = "Rohan Kapoor"
        result = await _reconcile(
            "INSURANCE",
            "HEALTH_CHECKUP_REPORT",
            _draw_health_checkup,
            fields,
            "checkup_table",
            6110,
            {"name": "Ananya Verma"},
        )
        assert len(result.conflicts) == 1
        assert result.conflicts[0].ambiguity_id == "AMB_PRE_EXISTING_ILLNESS"
        assert result.verified is False
        assert result.auxiliary_facts.get("name", "").startswith("Rohan Kapoor")

    async def test_matching_name_no_conflict(self):
        from app.docai.dataset.generate_insurance import _draw_health_checkup, _make_fields

        rng = random.Random(20260931)
        fake = Faker()
        Faker.seed(20260931)
        fields = _make_fields(rng, fake, "HEALTH_CHECKUP_REPORT")
        fields["name"] = "Meera Nair"
        result = await _reconcile(
            "INSURANCE",
            "HEALTH_CHECKUP_REPORT",
            _draw_health_checkup,
            fields,
            "checkup_table",
            6113,
            {"name": "meera nair"},
        )
        assert result.conflicts == []


@pytest.mark.skipif(get_classifier("ACCOUNT_OPENING") is None, reason="No trained classifier.")
class TestAccountOpeningConsistency:
    """No evidence_mappings target_field in this manifest has ANY
    matching ambiguity_rule at all (AMB_NOMINEE_RELATION ->
    nominee_declared, AMB_FATCA_STATUS -> identity_verified - neither is
    an evidence-driven field) - a genuine name conflict is detected but
    can never be surfaced for this journey, and that's the honest,
    correct behavior rather than a fabricated wiring."""

    async def test_name_conflict_detected_but_never_surfaceable(self):
        from app.docai.dataset.generate_account_opening import _draw_pan_card, _make_fields

        rng = random.Random(20260929)
        fake = Faker()
        Faker.seed(20260929)
        fields = _make_fields(rng, fake, "PAN_CARD_IMAGE")
        fields["name"] = "Different Person"
        result = await _reconcile(
            "ACCOUNT_OPENING",
            "PAN_CARD_IMAGE",
            _draw_pan_card,
            fields,
            "pan_standard",
            6111,
            {"name": "Original Applicant"},
        )
        assert result.conflicts == []
        assert result.auxiliary_facts.get("name") == "Different Person"


@pytest.mark.skipif(get_classifier("LENDING") is None, reason="No trained classifier.")
class TestLendingConsistency:
    """monthly_income and employer_name (both real state_schema fields)
    already have working, tested consistency (integrity-hardening
    phase). This class covers the NEW auxiliary "name" comparison
    specifically - SALARY_SLIP's target (monthly_income) has a matching
    ambiguity_rule (INCOME_MISMATCH), whose question is about income, not
    identity - same disclosed topic-mismatch limitation as KYC/Insurance,
    but the conflict is still correctly detected and surfaced."""

    async def test_name_conflict_is_detected_and_surfaced_with_a_topic_mismatched_rule(self):
        from app.docai.dataset.generate import _draw_salary_slip, _make_fields

        rng = random.Random(20260930)
        fake = Faker()
        Faker.seed(20260930)
        fields = _make_fields(rng, fake, "SALARY_SLIP", "symbol")
        fields["name"] = "Different Employee"
        # clean=True: a real-OCR run at this exact seed was traced to
        # additionally hit the already-disclosed currency-symbol/extra-
        # leading-digit artifact on the Gross/Deductions figures, adding a
        # SECOND, spurious INCOME_MISMATCH(monthly_income) conflict
        # alongside the intentional name conflict this test isolates -
        # unrelated to the consistency mechanism under test here.
        result = await _reconcile(
            "LENDING",
            "SALARY_SLIP",
            _draw_salary_slip,
            fields,
            "salary_table",
            6112,
            {"name": "Original Applicant"},
            clean=True,
        )
        assert len(result.conflicts) == 1
        assert result.conflicts[0].ambiguity_id == "INCOME_MISMATCH"
        assert result.verified is False
        assert result.auxiliary_facts.get("name") == "Different Employee"

    async def test_matching_name_no_conflict(self):
        from app.docai.dataset.generate import _draw_salary_slip, _make_fields

        rng = random.Random(20260932)
        fake = Faker()
        Faker.seed(20260932)
        fields = _make_fields(rng, fake, "SALARY_SLIP", "symbol")
        fields["name"] = "Kevin Brooks"
        result = await _reconcile(
            "LENDING",
            "SALARY_SLIP",
            _draw_salary_slip,
            fields,
            "salary_table",
            6114,
            {"name": "kevin brooks"},
        )
        assert result.conflicts == []


@pytest.mark.skipif(get_classifier("INVESTMENT") is None, reason="No trained classifier.")
class TestLowConfidenceExtractionGate:
    """Mission requirement (Part 6 Case G): an uncertain/malformed
    extraction must not manufacture a strong contradiction. Gated on
    `field.validated` in app/ai/local_ml.py - a malformed identifier
    (wrong length/shape) never even reaches the comparison, regardless
    of how different it looks from the prior recorded value."""

    async def test_malformed_identifier_never_triggers_a_conflict(self):
        manifest = pack_registry.get_pack("INVESTMENT")
        provider = LocalMLProvider()
        ocr_meta = {"confidence": 0.95, "word_count": 20, "lines": []}
        # "PAN: ABCDE12" is too short to validate as a real PAN shape -
        # extraction must report validated=False and never compare it.
        text = (
            "KRA KYC Validation Letter\nName: Test Person\nPAN: ABCDE12\nRegistered on: 01/01/2020"
        )
        result = await provider.reconcile_evidence(
            doc_type="KRA_KYC_LETTER",
            extracted_text=text,
            manifest=manifest,
            existing_fields={"identifier::KRA_KYC_LETTER": "ZZZZZ9999Z"},
            ocr_meta=ocr_meta,
        )
        assert result.conflicts == []
        assert "identifier::KRA_KYC_LETTER" not in result.auxiliary_facts
