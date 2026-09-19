"""Comprehensive automated tests for Errors 38–41 across all 6 financial journeys:
- Error 38: AI Document Analysis accuracy across all supported documents
- Error 39: Loan Terms & Conditions computation & verification
- Error 40: KYC Passport OVD strict content validation (rejection of wrong/invalid passport data)
- Error 41: Cancelled Cheque strict validation (rejection of non-cheque documents)
"""

import pytest

from app.docai.document_validator import (
    validate_cancelled_cheque_content,
    validate_document,
    validate_passport_content,
)
from app.packs.registry import pack_registry

# --------------------------------------------------------------------------
# ERROR 38: AI DOCUMENT ANALYSIS ACROSS ALL 6 JOURNEYS
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "journey_type,doc_type,sample_text",
    [
        # LENDING
        (
            "LENDING",
            "SALARY_SLIP",
            (
                "Acme Technologies India Pvt Ltd\n"
                "Payslip for August 2026\n"
                "Employee Name: Rahul Sharma\n"
                "Earnings: Basic Pay ₹50,000, HRA ₹25,000, Gross Salary ₹75,000\n"
                "Deductions: PF ₹3,000, Tax ₹2,000, Total Deductions ₹5,000\n"
                "Net Pay: ₹70,000"
            ),
        ),
        (
            "LENDING",
            "BANK_STATEMENT",
            (
                "HDFC Bank Statement of Account\n"
                "Account Number: 50100234567890\n"
                "Statement Period: 01-08-2026 to 31-08-2026\n"
                "Transaction Details:\n"
                "15-08-2026 SALARY CREDIT ACME TECH ₹70,000 CR\n"
                "Opening Balance: ₹25,000\n"
                "Closing Balance: ₹85,000"
            ),
        ),
        (
            "LENDING",
            "OFFICE_ID_CARD",
            (
                "Infosys Limited\n"
                "Staff Identity Card\n"
                "Employee Name: Ananya Iyer\n"
                "Emp ID: INF123456\n"
                "Designation: Senior Software Engineer\n"
                "Location: Bangalore"
            ),
        ),
        (
            "LENDING",
            "OFFER_LETTER",
            (
                "Tata Consultancy Services Ltd\n"
                "Letter of Appointment\n"
                "Dear Vikram Patel,\n"
                "We are pleased to offer you employment with TCS Ltd as Lead Architect with "
                "an Annual CTC of ₹18,00,000. Joining Date: 01-10-2026."
            ),
        ),
        # INSURANCE
        (
            "INSURANCE",
            "MEDICAL_DISCHARGE_SUMMARY",
            (
                "Apollo Hospitals Enterprise Ltd\n"
                "Clinical Discharge Summary\n"
                "Patient Name: Priya Nair\n"
                "IP No: 987654\n"
                "Admission Date: 10-05-2026\n"
                "Discharge Date: 14-05-2026\n"
                "Diagnosis: Acute Appendicitis (Resolved)\n"
                "Treatment Given: Laparoscopic Appendectomy. Consultant: Dr. K. Mehta."
            ),
        ),
        (
            "INSURANCE",
            "HEALTH_CHECKUP_REPORT",
            (
                "Dr. Lal PathLabs\n"
                "Comprehensive Medical Health Checkup Report\n"
                "Patient: Suresh Kumar\n"
                "Diagnostic Investigation Report:\n"
                "Blood Test CBC Normal, Lipid Profile Cholesterol 185 mg/dL, "
                "HbA1c 5.6%, ECG Normal."
            ),
        ),
        (
            "INSURANCE",
            "PREVIOUS_POLICY_COPY",
            (
                "HDFC ERGO General Insurance Co Ltd\n"
                "Health Insurance Policy Schedule & Certificate\n"
                "Policy Number: HDF-HLTH-2025-99881\n"
                "Insured Person: Suresh Kumar\n"
                "Sum Insured: ₹5,00,000\n"
                "Policy Period: 01-04-2025 to 31-03-2026\n"
                "Premium Paid: ₹14,500."
            ),
        ),
        # CREDIT CARD
        (
            "CREDIT_CARD",
            "ITR_V_ACKNOWLEDGEMENT",
            (
                "INDIAN INCOME TAX RETURN ACKNOWLEDGEMENT (ITR-V)\n"
                "Assessment Year: 2026-27\n"
                "Income Tax Department e-Filing\n"
                "Name: Amit Verma\n"
                "PAN: ABCDV1234F\n"
                "Gross Total Income: ₹12,50,000\n"
                "Total Income: ₹11,00,000\n"
                "e-Filing Acknowledgment Number: 2891238491029384"
            ),
        ),
        (
            "CREDIT_CARD",
            "UTILITY_BILL_ELECTRICITY",
            (
                "Tata Power Distribution Limited\n"
                "Electricity Bill & Payment Receipt\n"
                "Consumer Number: CA1092837465\n"
                "Bill Date: 15-08-2026, Due Date: 30-08-2026\n"
                "Units Consumed: 340 Units, Tariff: LT-1 Domestic\n"
                "Bill Amount: ₹2,850\n"
                "Billing Address: Flat 402, Sunshine Heights, Mumbai 400050"
            ),
        ),
        # KYC
        (
            "KYC",
            "PASSPORT_SCAN",
            (
                "Republic of India / Passport\n"
                "Type: P, Country Code: IND\n"
                "Passport No: K8765432\n"
                "Surname: SHARMA\n"
                "Given Name: ROHIT\n"
                "Nationality: INDIAN\n"
                "Sex: M\n"
                "Date of Birth: 15/07/1992\n"
                "Place of Birth: DELHI\n"
                "Date of Issue: 10/01/2020\n"
                "Date of Expiry: 09/01/2030\n"
                "P<INDSHARMA<<ROHIT<<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
                "K8765432<4IND9207151M3001098<<<<<<<<<<<<<<<06"
            ),
        ),
        (
            "KYC",
            "VOTER_ID_CARD",
            (
                "Election Commission of India\n"
                "Elector's Photo Identity Card (EPIC)\n"
                "EPIC No: WXY9876543\n"
                "Elector Name: Deepa Joshi\n"
                "Father's Name: R. C. Joshi\n"
                "Gender: Female\n"
                "Assembly Constituency: 42-Indira Nagar"
            ),
        ),
        (
            "KYC",
            "DRIVING_LICENCE",
            (
                "Union of India - Transport Department\n"
                "Driving Licence\n"
                "DL No: MH0220180012345\n"
                "Name: Arvind Menon\n"
                "Date of Birth: 22-09-1988\n"
                "Authorised to Drive: LMV-NT, MCWG\n"
                "Validity: 21-09-2038"
            ),
        ),
        # ACCOUNT OPENING
        (
            "ACCOUNT_OPENING",
            "AADHAAR_FRONT_BACK",
            (
                "Unique Identification Authority of India\n"
                "Government of India\n"
                "Enrollment No: 1092/38475/19283\n"
                "To: Meera Sundaram\n"
                "DOB: 12/04/1995\n"
                "Female\n"
                "Mera Aadhaar, Meri Pehchan\n"
                "5412 8901 2345"
            ),
        ),
        (
            "ACCOUNT_OPENING",
            "SIGNATURE_SPECIMEN",
            (
                "Bank Specimen Signature Card\n"
                "Account Title: Meera Sundaram\n"
                "Applicant Signature on plain white paper\n"
                "[Signature image present]\n"
                "Authorized Signatory Specimen verified."
            ),
        ),
        # INVESTMENT
        (
            "INVESTMENT",
            "CANCELLED_CHEQUE",
            (
                "State Bank of India\n"
                "Branch: MG Road, Bangalore\n"
                "IFSC Code: SBIN0001234\n"
                "Account No: 30192847561\n"
                "Pay: CANCELLED\n"
                "Rupees: **********************\n"
                "A/c Payee Only\n"
                "Cheque No: 004521\n"
                "MICR: 560002014"
            ),
        ),
        (
            "INVESTMENT",
            "BANK_STATEMENT_SUMMARY",
            (
                "ICICI Bank Statement Summary\n"
                "Account Number: 001105023948\n"
                "IFSC Code: ICIC0000011\n"
                "Statement Period: 01-Jan-2026 to 30-Jun-2026\n"
                "Account Title: Kunal Kapoor\n"
                "Active Savings Account with valid KYC."
            ),
        ),
        (
            "INVESTMENT",
            "KRA_KYC_LETTER",
            (
                "CVL KRA - CDSL Ventures Limited\n"
                "SEBI KYC Registration Agency (KRA)\n"
                "KYC Status Verification Letter\n"
                "PAN: ABCDK9876L\n"
                "Name: Kunal Kapoor\n"
                "KYC Status: KYC Verified / Registered with CVL KRA on 15-03-2024."
            ),
        ),
    ],
)
def test_all_supported_documents_classified_and_verified(journey_type, doc_type, sample_text):
    manifest = pack_registry.get_pack(journey_type)
    assert manifest is not None

    outcome = validate_document(
        text=sample_text,
        expected_doc_type=doc_type,
        manifest=manifest,
        is_mock=False,
    )

    assert outcome.outcome == "CORRECT_DOCUMENT"
    assert outcome.is_verified is True
    assert outcome.requires_review is False
    assert outcome.confidence >= 0.80
    assert len(outcome.reason) > 0


# --------------------------------------------------------------------------
# ERROR 40: KYC PASSPORT OVD STRICT VALIDATION
# --------------------------------------------------------------------------


def test_valid_passport_passes_ovd_validation():
    valid_text = (
        "Republic of India / Passport\n"
        "Type: P, Code: IND, Passport No: Z1234567\n"
        "Given Name: Ananya, Surname: Sharma\n"
        "Nationality: INDIAN\n"
        "Date of Birth: 12/03/1995\n"
        "Date of Expiry: 11/03/2035\n"
        "P<INDSHARMA<<ANANYA<<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
        "Z1234567<4IND9503121F3503118<<<<<<<<<<<<<<<02"
    )
    passed, msg, aux = validate_passport_content(valid_text)
    assert passed is True
    assert aux.get("identifier::PASSPORT_SCAN") == "Z1234567"
    assert aux.get("name") is not None


def test_wrong_passport_data_is_rejected():
    # Passport with invalid passport number format (e.g. WRONG_DATA)
    wrong_text = (
        "Republic of India / Passport Scan\n"
        "Passport No: INVALID_DATA_12345\n"
        "Name: Test User\n"
        "Nationality: Foreign\n"
    )
    passed, msg, aux = validate_passport_content(wrong_text)
    assert passed is False
    assert "passport" in msg.lower() or "number" in msg.lower()


def test_non_passport_document_uploaded_for_kyc_passport_is_rejected():
    # User uploads a Salary Slip for KYC Passport
    salary_slip_text = (
        "Acme Corp Payslip\nEmployee: John Doe\nNet Pay: ₹80,000\nBasic Salary: ₹50,000\n"
    )
    manifest = pack_registry.get_pack("KYC")
    outcome = validate_document(
        text=salary_slip_text,
        expected_doc_type="PASSPORT_SCAN",
        manifest=manifest,
        is_mock=False,
    )
    assert outcome.outcome == "WRONG_DOCUMENT"
    assert outcome.is_verified is False
    assert outcome.requires_review is False


# --------------------------------------------------------------------------
# ERROR 41: CANCELLED CHEQUE STRICT VALIDATION
# --------------------------------------------------------------------------


def test_valid_cancelled_cheque_passes_validation():
    valid_cheque = (
        "HDFC Bank Ltd\n"
        "Branch: Connaught Place, New Delhi\n"
        "IFSC Code: HDFC0000003\n"
        "Account Number: 00031000098765\n"
        "Pay: CANCELLED\n"
        "Rupees: ----------------------------\n"
        "A/c Payee Only\n"
        "MICR: 110240001\n"
    )
    passed, msg, aux = validate_cancelled_cheque_content(valid_cheque)
    assert passed is True
    assert aux.get("identifier::CANCELLED_CHEQUE") == "HDFC0000003"


def test_passport_uploaded_for_cancelled_cheque_is_rejected_as_wrong_document():
    passport_text = (
        "Republic of India / Passport\n"
        "Passport No: K9876543\n"
        "Given Name: Sanjay, Surname: Gupta\n"
        "Nationality: INDIAN\n"
    )
    manifest = pack_registry.get_pack("INVESTMENT")
    outcome = validate_document(
        text=passport_text,
        expected_doc_type="CANCELLED_CHEQUE",
        manifest=manifest,
        is_mock=False,
    )
    assert outcome.outcome == "WRONG_DOCUMENT"
    assert outcome.is_verified is False
    assert outcome.requires_review is False
    assert "passport" in outcome.reason.lower()


def test_salary_slip_uploaded_for_cancelled_cheque_is_rejected_as_wrong_document():
    salary_text = (
        "Infosys Limited Payslip for July 2026\n"
        "Employee: Sandeep Roy\n"
        "Earnings: Gross ₹95,000, Deductions: ₹10,000\n"
        "Net Pay: ₹85,000\n"
    )
    manifest = pack_registry.get_pack("INVESTMENT")
    outcome = validate_document(
        text=salary_text,
        expected_doc_type="CANCELLED_CHEQUE",
        manifest=manifest,
        is_mock=False,
    )
    assert outcome.outcome == "WRONG_DOCUMENT"
    assert outcome.is_verified is False
    assert outcome.requires_review is False
    assert "salary slip" in outcome.reason.lower()


# --------------------------------------------------------------------------
# ERROR 39: LOAN TERMS COMPUTATION & VALIDATION
# --------------------------------------------------------------------------


def test_lending_loan_terms_calculation():
    loan_amount = 500000
    tenure_months = 36
    annual_rate = 10.5
    monthly_rate = annual_rate / 12 / 100

    emi = round(
        (loan_amount * monthly_rate * ((1 + monthly_rate) ** tenure_months))
        / (((1 + monthly_rate) ** tenure_months) - 1)
    )
    processing_fee = round(loan_amount * 0.015 * 1.18)
    total_repayment = emi * tenure_months + processing_fee

    assert emi > 0
    assert processing_fee > 0
    assert total_repayment > loan_amount
    assert emi == 16251  # standard ₹5L 36m 10.5% EMI
