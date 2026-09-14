"""PaytmFlow Document Intelligence (docai).

Real, local, self-controlled document AI: preprocessing, OCR, document
classification, structured extraction, deterministic validation, and
cross-document consistency checking.

This package contains the actual ML/DL machinery. `app/ai/local_ml.py`
is the thin adapter that exposes it through the existing `AIProvider`
Protocol (app/ai/provider.py) so the deterministic engine, guardrails,
and wire schemas are completely unchanged.

Scope note (2026-09): dataset, training, and evaluation are now built and
measured for all six packs:
  - LENDING: 4 evidence doc types (SALARY_SLIP, BANK_STATEMENT,
    OFFICE_ID_CARD, OFFER_LETTER), MONEY/TEXT evidence_mappings targets.
  - INSURANCE: 3 evidence doc types (MEDICAL_DISCHARGE_SUMMARY,
    HEALTH_CHECKUP_REPORT, PREVIOUS_POLICY_COPY), a single BOOLEAN
    evidence_mappings target (`ped_declaration_submitted`) - a
    structurally different shape from Lending's, which exercised a real
    gap in the original (Lending-only) boolean-handling code, fixed
    while building Insurance rather than assumed away.
  - KYC: 3 evidence doc types (PASSPORT_SCAN, VOTER_ID_CARD,
    DRIVING_LICENCE), also a single BOOLEAN target
    (`ovd_document_uploaded`, confirming the boolean-target fix
    generalizes with zero new provider code) - but the first pack whose
    documents carry real, format-validated government identifiers
    (passport/EPIC/DL numbers), extracted and validated by
    `extraction.py::extract_identifier`.
  - CREDIT_CARD: 3 evidence doc types (SALARY_SLIP, ITR_V_ACKNOWLEDGEMENT,
    UTILITY_BILL_ELECTRICITY), a single BOOLEAN target shared by two
    alternate-evidence doc types (`income_verified`, satisfied by either
    SALARY_SLIP or ITR_V_ACKNOWLEDGEMENT via different action_ids) plus a
    second BOOLEAN target (`current_address_verified`), again with zero
    new provider code - and the first pack whose identifier is a PAN
    (5-letter-prefix + 4-digit + 1-letter format), proving
    `extract_identifier`'s framework generalizes to a third distinct
    identifier shape via a data-driven pattern addition only.
  - ACCOUNT_OPENING: 3 evidence doc types (SIGNATURE_SPECIMEN,
    PAN_CARD_IMAGE, AADHAAR_FRONT_BACK), again zero new provider code -
    the first pack whose identifier has NO letters at all (Aadhaar: 12
    digits) and the first whose real-world document content is mostly a
    handwritten mark rather than printed text (SIGNATURE_SPECIMEN).
    `AADHAAR_FRONT_BACK`'s routing defect (its action's `accepts` held a
    MIME type, `image/png`, instead of a doc_type) was fixed in the
    manifest-integrity + confidence-calibration phase, confirmed
    unambiguous by the frozen contract and the frontend's own
    `accepts[0]`-as-doc_type behavior. `PAN_CARD_IMAGE`'s
    `evidence_mappings.action_id` still doesn't correctly route to an
    action satisfying its claimed `target_field` - disclosed and left
    unfixed, since no EVIDENCE action exists that satisfies
    `pan_authenticated` to repoint it to without inventing one (see
    docs/docai_manifest_confidence_report.md §1).
  - INVESTMENT: 3 evidence doc types (CANCELLED_CHEQUE,
    BANK_STATEMENT_SUMMARY, KRA_KYC_LETTER), the sixth and final pack,
    again zero new provider code. Two more new identifier shapes: IFSC
    (4-letter bank code + digit branch code) and a bare bank account
    number (digits only). Surfaced and fixed one systemic bug affecting
    EVERY journey's identifier extraction, not just Investment's: the
    `\\s?` separators inside `extraction.py`'s identifier value patterns
    could match a newline, letting a trailing-letter group latch onto a
    leading capital letter from the NEXT, unrelated printed line -
    tightened to `[ \\t]?` everywhere (see
    docs/docai_investment_report.md §6 for the full trace). Also the
    second pack found to have a genuine `evidence_mappings` ROUTING
    defect (KRA_KYC_LETTER's `action_id` doesn't match its claimed
    target field) - disclosed, not fixed, same reasoning as Account
    Opening's.
The pipeline itself (ocr.py, classifier.py, extraction.py, normalize.py,
confidence.py, consistency.py) is journey-agnostic - it reads doc types
and target fields from each manifest's own `evidence_mappings` at
runtime, not from hardcoded journey checks. Until a pack has trained
model artifacts, LocalMLProvider reports a safe low-confidence "not yet
analyzed" result rather than fabricating output - no pack currently
lacks one.
"""
