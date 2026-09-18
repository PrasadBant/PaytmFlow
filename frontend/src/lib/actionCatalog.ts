import type { components } from '@/api/types.gen';

type ActionOption = components['schemas']['ActionOption'];

/**
 * Fallback action catalog across all 6 journey packs.
 * Used when direct navigation to /act/:actionId occurs and action metadata
 * is not passed in location.state or recommendation response.
 */
export const ACTION_CATALOG: Record<string, ActionOption> = {
  // LENDING
  upload_income_proof: {
    action_id: 'upload_income_proof',
    kind: 'EVIDENCE',
    title: 'Upload Income Proof',
    why: 'Required to assess loan eligibility and repayment capacity',
    accepts: ['SALARY_SLIP', 'BANK_STATEMENT', 'ITR_V'],
    unlocks: ['income_verified'],
  },
  UPLOAD_INCOME_PROOF: {
    action_id: 'UPLOAD_INCOME_PROOF',
    kind: 'EVIDENCE',
    title: 'Upload Income Proof',
    why: 'Required to assess loan eligibility and repayment capacity',
    accepts: ['SALARY_SLIP', 'BANK_STATEMENT', 'ITR_V'],
    unlocks: ['income_verified'],
  },
  link_aa_account: {
    action_id: 'link_aa_account',
    kind: 'FORM',
    title: 'Link Bank via Account Aggregator',
    why: 'Instant automated bank statement fetch through RBI Account Aggregator framework',
    input_schema: [
      {
        key: 'aa_consent_handle',
        type: 'text',
        label: 'Account Aggregator Consent Handle',
        required: true,
        placeholder: 'e.g. AA-CONSENT-98765',
      },
    ],
    unlocks: ['income_verified'],
  },
  submit_employment_info: {
    action_id: 'submit_employment_info',
    kind: 'FORM',
    title: 'Declare Employer Details',
    why: 'Current employer name required to verify employment stability',
    input_schema: [
      {
        key: 'employer_name',
        type: 'text',
        label: 'Current Employer / Company Name',
        required: true,
        placeholder: 'e.g. Infosys Ltd',
      },
    ],
    unlocks: ['employer_name_declared'],
  },
  SUBMIT_EMPLOYMENT_INFO: {
    action_id: 'SUBMIT_EMPLOYMENT_INFO',
    kind: 'FORM',
    title: 'Declare Employer Details',
    why: 'Current employer name required to verify employment stability',
    input_schema: [
      {
        key: 'employer_name',
        type: 'text',
        label: 'Current Employer / Company Name',
        required: true,
        placeholder: 'e.g. Infosys Ltd',
      },
    ],
    unlocks: ['employer_name_declared'],
  },
  verify_employer_record: {
    action_id: 'verify_employer_record',
    kind: 'FORM',
    title: 'Verify Employment via EPFO',
    why: 'Instant EPFO UAN check confirms active employment status',
    input_schema: [
      {
        key: 'epfo_uan',
        type: 'text',
        label: 'EPFO Universal Account Number (UAN)',
        required: true,
        placeholder: 'e.g. 100904812345',
      },
    ],
    unlocks: ['employment_verified'],
  },
  accept_loan_agreement: {
    action_id: 'accept_loan_agreement',
    kind: 'FORM',
    title: 'Review & Accept Loan Agreement',
    why: 'Binding acceptance of loan terms, interest rate, and EMI schedule',
    input_schema: [
      {
        key: 'accept_terms',
        type: 'boolean',
        label: 'I accept the loan terms and conditions, interest rate, and repayment schedule',
        required: true,
      },
    ],
    unlocks: ['loan_offer_accepted'],
  },
  ACCEPT_LOAN_TERMS: {
    action_id: 'ACCEPT_LOAN_TERMS',
    kind: 'FORM',
    title: 'Review & Accept Loan Agreement',
    why: 'Binding acceptance of loan terms, interest rate, and EMI schedule',
    input_schema: [
      {
        key: 'accept_terms',
        type: 'boolean',
        label: 'I accept the loan terms and conditions, interest rate, and repayment schedule',
        required: true,
      },
    ],
    unlocks: ['loan_offer_accepted'],
  },

  // CREDIT CARD
  submit_income_for_card: {
    action_id: 'submit_income_for_card',
    kind: 'EVIDENCE',
    title: 'Upload Income Proof',
    why: 'Required to assess credit limit and card eligibility',
    accepts: ['SALARY_SLIP', 'ITR_V', 'FORM_16'],
    unlocks: ['income_verified'],
  },
  submit_digital_salary_slip: {
    action_id: 'submit_digital_salary_slip',
    kind: 'EVIDENCE',
    title: 'Upload Latest Salary Slip',
    why: 'Recent salary slip with employer name and net pay',
    accepts: ['SALARY_SLIP'],
    unlocks: ['income_verified'],
  },
  link_account_aggregator: {
    action_id: 'link_account_aggregator',
    kind: 'FORM',
    title: 'Link Bank via Account Aggregator',
    why: 'Instant automated bank statement fetch for income verification',
    input_schema: [
      {
        key: 'aa_consent_handle',
        type: 'text',
        label: 'Account Aggregator Consent Handle',
        required: true,
        placeholder: 'e.g. AA-CONSENT-12345',
      },
    ],
    unlocks: ['income_verified'],
  },
  provide_employment_info: {
    action_id: 'provide_employment_info',
    kind: 'FORM',
    title: 'Provide Employment Details',
    why: 'Employer name and monthly income for credit card underwriting',
    input_schema: [
      {
        key: 'employer_name',
        type: 'text',
        label: 'Employer / Business Name',
        required: true,
        placeholder: 'e.g. Tata Consultancy Services',
      },
      {
        key: 'monthly_net_income',
        type: 'money',
        label: 'Monthly Net Income (₹)',
        required: true,
        min: 15000,
        placeholder: 'e.g. 65000',
      },
    ],
    unlocks: ['employment_verified'],
  },
  verify_employment_details: {
    action_id: 'verify_employment_details',
    kind: 'FORM',
    title: 'Provide Employment Details',
    why: 'Employer name and monthly income for credit card underwriting',
    input_schema: [
      {
        key: 'employer_name',
        type: 'text',
        label: 'Employer / Business Name',
        required: true,
        placeholder: 'e.g. Tata Consultancy Services',
      },
      {
        key: 'monthly_net_income',
        type: 'money',
        label: 'Monthly Net Income (₹)',
        required: true,
        min: 15000,
        placeholder: 'e.g. 65000',
      },
    ],
    unlocks: ['employment_verified'],
  },
  confirm_dispatch_address: {
    action_id: 'confirm_dispatch_address',
    kind: 'FORM',
    title: 'Confirm Delivery Address',
    why: 'Physical address where your card and welcome kit will be delivered',
    input_schema: [
      {
        key: 'address_line1',
        type: 'text',
        label: 'House / Flat / Building, Street',
        required: true,
        placeholder: 'e.g. Flat 402, Sunshine Heights',
      },
      {
        key: 'address_line2',
        type: 'text',
        label: 'Area / Sector / Landmark',
        required: false,
        placeholder: 'e.g. Near City Center Mall',
      },
      {
        key: 'city',
        type: 'text',
        label: 'City',
        required: true,
        placeholder: 'e.g. Mumbai',
      },
      {
        key: 'pincode',
        type: 'text',
        label: 'PIN Code (6 digits)',
        required: true,
        placeholder: 'e.g. 400001',
      },
    ],
    unlocks: ['delivery_address_confirmed'],
  },
  accept_cardholder_agreement: {
    action_id: 'accept_cardholder_agreement',
    kind: 'FORM',
    title: 'Accept Cardholder Agreement',
    why: 'Binding acceptance of Most Important Terms and Conditions (MITC) and card charges',
    input_schema: [
      {
        key: 'accept_card_terms',
        type: 'boolean',
        label: 'I accept the Cardholder Agreement, Schedule of Charges, and MITC',
        required: true,
      },
    ],
    unlocks: ['card_agreement_signed'],
  },
  sign_cardholder_agreement: {
    action_id: 'sign_cardholder_agreement',
    kind: 'FORM',
    title: 'Accept Cardholder Agreement',
    why: 'Binding acceptance of Most Important Terms and Conditions (MITC) and card charges',
    input_schema: [
      {
        key: 'accept_card_terms',
        type: 'boolean',
        label: 'I accept the Cardholder Agreement, Schedule of Charges, and MITC',
        required: true,
      },
    ],
    unlocks: ['card_agreement_signed'],
  },

  // HEALTH INSURANCE
  declare_medical_history: {
    action_id: 'declare_medical_history',
    kind: 'FORM',
    title: 'Complete Health Questionnaire',
    why: 'Disclose existing health conditions for accurate premium and underwriting',
    input_schema: [
      {
        key: 'has_hypertension',
        type: 'boolean',
        label: 'Have you been diagnosed with high blood pressure / hypertension?',
        required: true,
      },
      {
        key: 'has_diabetes',
        type: 'boolean',
        label: 'Have you been diagnosed with diabetes or high blood sugar?',
        required: true,
      },
      {
        key: 'has_critical_illness',
        type: 'boolean',
        label: 'Any history of cancer, cardiac condition, or kidney disease?',
        required: true,
      },
      {
        key: 'has_surgeries',
        type: 'boolean',
        label: 'Any major surgery or hospitalization in the last 4 years?',
        required: true,
      },
    ],
    unlocks: ['medical_history_declared'],
  },
  submit_medical_declaration: {
    action_id: 'submit_medical_declaration',
    kind: 'FORM',
    title: 'Complete Health Questionnaire',
    why: 'Disclose existing health conditions for accurate premium and underwriting',
    input_schema: [
      {
        key: 'has_hypertension',
        type: 'boolean',
        label: 'Have you been diagnosed with high blood pressure / hypertension?',
        required: true,
      },
      {
        key: 'has_diabetes',
        type: 'boolean',
        label: 'Have you been diagnosed with diabetes or high blood sugar?',
        required: true,
      },
      {
        key: 'has_critical_illness',
        type: 'boolean',
        label: 'Any history of cancer, cardiac condition, or kidney disease?',
        required: true,
      },
      {
        key: 'has_surgeries',
        type: 'boolean',
        label: 'Any major surgery or hospitalization in the last 4 years?',
        required: true,
      },
    ],
    unlocks: ['medical_history_declared'],
  },
  submit_ped_clearance: {
    action_id: 'submit_ped_clearance',
    kind: 'EVIDENCE',
    title: 'Upload Hospital Discharge Summary',
    why: 'Medical records to evaluate pre-existing condition severity',
    accepts: ['DISCHARGE_SUMMARY', 'DOCTOR_PRESCRIPTION'],
    unlocks: ['ped_declaration_submitted'],
  },
  submit_ped_exemption: {
    action_id: 'submit_ped_exemption',
    kind: 'EVIDENCE',
    title: 'Upload Hospital Discharge Summary',
    why: 'Medical records to evaluate pre-existing condition severity',
    accepts: ['DISCHARGE_SUMMARY', 'DOCTOR_PRESCRIPTION'],
    unlocks: ['ped_declaration_submitted'],
  },
  confirm_zero_ped: {
    action_id: 'confirm_zero_ped',
    kind: 'FORM',
    title: 'Confirm No Pre-existing Conditions',
    why: 'Self-declaration when no pre-existing illnesses apply',
    input_schema: [
      {
        key: 'no_pre_existing_conditions',
        type: 'boolean',
        label: 'I confirm that I have no pre-existing conditions or ongoing chronic treatments',
        required: true,
      },
    ],
    unlocks: ['ped_declaration_submitted'],
  },
  schedule_tele_mer: {
    action_id: 'schedule_tele_mer',
    kind: 'FORM',
    title: 'Schedule Tele-Medical Consultation',
    why: 'Short 10-minute doctor phone consultation required for high coverage',
    input_schema: [
      {
        key: 'preferred_slot',
        type: 'text',
        label: 'Preferred Date & Time Window',
        required: true,
        placeholder: 'e.g. Tomorrow 10:00 AM - 12:00 PM',
      },
    ],
    unlocks: ['tele_mer_completed'],
  },
  setup_insurance_mandate: {
    action_id: 'setup_insurance_mandate',
    kind: 'FORM',
    title: 'Set Up Auto-Debit Mandate',
    why: 'Recurring bank mandate for automated policy renewal',
    input_schema: [
      {
        key: 'bank_account_number',
        type: 'text',
        label: 'Bank Account Number',
        required: true,
        placeholder: 'e.g. 123456789012',
      },
      {
        key: 'ifsc_code',
        type: 'text',
        label: 'Bank IFSC Code',
        required: true,
        placeholder: 'e.g. HDFC0001234',
      },
      {
        key: 'account_holder_name',
        type: 'text',
        label: 'Account Holder Name',
        required: true,
        placeholder: 'e.g. Ramesh Kumar',
      },
    ],
    unlocks: ['premium_payment_setup'],
  },
  confirm_policy_terms: {
    action_id: 'confirm_policy_terms',
    kind: 'FORM',
    title: 'Confirm Policy Terms & Nominee',
    why: 'Final consent to policy exclusions, waiting periods, and nominee assignment',
    input_schema: [
      {
        key: 'accept_policy_terms',
        type: 'boolean',
        label: 'I confirm accuracy of declarations and accept policy terms, waiting periods, and exclusions',
        required: true,
      },
    ],
    unlocks: ['policy_confirmed'],
  },
  accept_insurance_policy: {
    action_id: 'accept_insurance_policy',
    kind: 'FORM',
    title: 'Confirm Policy Terms & Nominee',
    why: 'Final consent to policy exclusions, waiting periods, and nominee assignment',
    input_schema: [
      {
        key: 'accept_policy_terms',
        type: 'boolean',
        label: 'I confirm accuracy of declarations and accept policy terms, waiting periods, and exclusions',
        required: true,
      },
    ],
    unlocks: ['policy_confirmed'],
  },

  // KYC
  upload_aadhaar_front_back: {
    action_id: 'upload_aadhaar_front_back',
    kind: 'EVIDENCE',
    title: 'Upload Aadhaar Card',
    why: 'Official Proof of Identity and Address under RBI Master Directions',
    accepts: ['AADHAAR_FRONT_BACK'],
    unlocks: ['aadhaar_verified'],
  },
  verify_pan_for_rekyc: {
    action_id: 'verify_pan_for_rekyc',
    kind: 'FORM',
    title: 'Link PAN Card',
    why: 'Mandatory income tax record validation for KYC refresh',
    input_schema: [
      {
        key: 'pan_number',
        type: 'text',
        label: 'Permanent Account Number (PAN)',
        required: true,
        placeholder: 'e.g. ABCDE1234F',
      },
    ],
    unlocks: ['pan_verified'],
  },
  link_pan_record: {
    action_id: 'link_pan_record',
    kind: 'FORM',
    title: 'Link PAN Card',
    why: 'Mandatory income tax record validation for KYC refresh',
    input_schema: [
      {
        key: 'pan_number',
        type: 'text',
        label: 'Permanent Account Number (PAN)',
        required: true,
        placeholder: 'e.g. ABCDE1234F',
      },
    ],
    unlocks: ['pan_verified'],
  },
  capture_liveness_selfie: {
    action_id: 'capture_liveness_selfie',
    kind: 'FORM',
    title: 'Take Liveness Selfie',
    why: 'Anti-spoofing face match against official identity document photo',
    input_schema: [
      {
        key: 'liveness_confirmed',
        type: 'boolean',
        label: 'I confirm this live camera image is mine and authorize biometrics comparison',
        required: true,
      },
    ],
    unlocks: ['liveness_confirmed'],
  },
  validate_gps_location: {
    action_id: 'validate_gps_location',
    kind: 'FORM',
    title: 'Confirm Geolocation within India',
    why: 'RBI mandate: customer must be within Indian territorial boundary during digital KYC',
    input_schema: [
      {
        key: 'location_confirmed',
        type: 'boolean',
        label: 'I confirm that I am currently located within India and allow GPS coordinate capture',
        required: true,
      },
    ],
    unlocks: ['geo_location_verified'],
  },
  confirm_digital_consent: {
    action_id: 'confirm_digital_consent',
    kind: 'FORM',
    title: 'Digital Consent Declaration',
    why: 'Accept terms of Aadhaar-based paperless digital KYC verification',
    input_schema: [
      {
        key: 'consent_confirmed',
        type: 'boolean',
        label: 'I hereby provide my explicit consent to re-verify my identity via digital KYC',
        required: true,
      },
    ],
    unlocks: ['consent_recorded'],
  },
  sign_rekyc_undertaking: {
    action_id: 'sign_rekyc_undertaking',
    kind: 'FORM',
    title: 'Digital Consent Declaration',
    why: 'Accept terms of Aadhaar-based paperless digital KYC verification',
    input_schema: [
      {
        key: 'consent_confirmed',
        type: 'boolean',
        label: 'I hereby provide my explicit consent to re-verify my identity via digital KYC',
        required: true,
      },
    ],
    unlocks: ['consent_recorded'],
  },

  // ACCOUNT OPENING
  verify_pan_for_banking: {
    action_id: 'verify_pan_for_banking',
    kind: 'FORM',
    title: 'Link PAN Card',
    why: 'Mandatory for opening Indian savings bank account',
    input_schema: [
      {
        key: 'pan_number',
        type: 'text',
        label: 'Permanent Account Number (PAN)',
        required: true,
        placeholder: 'e.g. ABCDE1234F',
      },
    ],
    unlocks: ['pan_authenticated'],
  },
  declare_account_nominee: {
    action_id: 'declare_account_nominee',
    kind: 'FORM',
    title: 'Add Account Nominee',
    why: 'Nominee designation for bank account operations',
    input_schema: [
      {
        key: 'nominee_name',
        type: 'text',
        label: 'Nominee Full Name',
        required: true,
        placeholder: 'e.g. Priya Sharma',
      },
      {
        key: 'nominee_relationship',
        type: 'enum',
        label: 'Relationship with Account Holder',
        required: true,
        options: [
          { value: 'SPOUSE', label: 'Spouse' },
          { value: 'PARENT', label: 'Parent' },
          { value: 'CHILD', label: 'Child' },
          { value: 'SIBLING', label: 'Sibling' },
          { value: 'OTHER', label: 'Other' },
        ],
      },
      {
        key: 'nominee_dob',
        type: 'text',
        label: 'Nominee Date of Birth (DD/MM/YYYY)',
        required: true,
        placeholder: 'e.g. 15/08/1990',
      },
    ],
    unlocks: ['nominee_declared'],
  },
  opt_out_nominee: {
    action_id: 'opt_out_nominee',
    kind: 'FORM',
    title: 'Opt-Out of Nominee',
    why: 'Explicitly opt out of appointing a nominee at account opening',
    input_schema: [
      {
        key: 'confirm_nominee_opt_out',
        type: 'boolean',
        label: 'I understand the benefits of nomination and explicitly choose not to add a nominee at this time',
        required: true,
      },
    ],
    unlocks: ['nominee_declared'],
  },
  upload_wet_signature: {
    action_id: 'upload_wet_signature',
    kind: 'EVIDENCE',
    title: 'Upload Specimen Signature',
    why: 'Clear photograph of physical signature on plain white paper',
    accepts: ['SIGNATURE_SPECIMEN'],
    unlocks: ['signature_uploaded'],
  },
  upload_digital_signature: {
    action_id: 'upload_digital_signature',
    kind: 'EVIDENCE',
    title: 'Sign on Screen (Digital Pad)',
    why: 'Draw digital signature directly on touchscreen',
    accepts: ['AADHAAR_FRONT_BACK'],
    unlocks: ['signature_uploaded'],
  },
  complete_video_kyc: {
    action_id: 'complete_video_kyc',
    kind: 'FORM',
    title: 'Start Video KYC Session',
    why: 'Live interactive agent verification per RBI guidelines',
    input_schema: [
      {
        key: 'vkyc_preferred_slot',
        type: 'text',
        label: 'Preferred Video KYC Time Window',
        required: true,
        placeholder: 'e.g. Today 2:00 PM - 3:00 PM',
      },
    ],
    unlocks: ['vkyc_completed'],
  },
  accept_banking_terms: {
    action_id: 'accept_banking_terms',
    kind: 'FORM',
    title: 'Accept Account Terms & Open',
    why: 'Consent to schedule of banking charges and debit card issuance',
    input_schema: [
      {
        key: 'accept_account_terms',
        type: 'boolean',
        label: 'I agree to the savings account rules, schedule of charges, and debit card terms',
        required: true,
      },
    ],
    unlocks: ['account_agreement_accepted'],
  },

  // INVESTMENT
  check_kra_status: {
    action_id: 'check_kra_status',
    kind: 'FORM',
    title: 'Validate Mutual Fund KYC',
    why: 'Verification against CVL / NDML KRA database',
    input_schema: [
      {
        key: 'pan_number',
        type: 'text',
        label: 'Permanent Account Number (PAN)',
        required: true,
        placeholder: 'e.g. ABCDE1234F',
      },
      {
        key: 'date_of_birth',
        type: 'text',
        label: 'Date of Birth (DD/MM/YYYY)',
        required: true,
        placeholder: 'e.g. 25/12/1992',
      },
    ],
    unlocks: ['kra_kyc_validated'],
  },
  complete_risk_questionnaire: {
    action_id: 'complete_risk_questionnaire',
    kind: 'FORM',
    title: 'Complete Risk Questionnaire',
    why: 'Assess investment horizon and risk tolerance profile',
    input_schema: [
      {
        key: 'investment_horizon',
        type: 'enum',
        label: 'Investment Time Horizon',
        required: true,
        options: [
          { value: 'SHORT_TERM', label: '1 to 3 Years (Capital Preservation)' },
          { value: 'MEDIUM_TERM', label: '3 to 5 Years (Balanced Growth)' },
          { value: 'LONG_TERM', label: 'More than 5 Years (Wealth Creation)' },
        ],
      },
      {
        key: 'risk_tolerance',
        type: 'enum',
        label: 'Risk Appetite',
        required: true,
        options: [
          { value: 'CONSERVATIVE', label: 'Low Risk / Conservative' },
          { value: 'MODERATE', label: 'Moderate Risk' },
          { value: 'AGGRESSIVE', label: 'High Risk / Aggressive Growth' },
        ],
      },
    ],
    unlocks: ['risk_assessment_completed'],
  },
  upload_cancelled_cheque: {
    action_id: 'upload_cancelled_cheque',
    kind: 'EVIDENCE',
    title: 'Upload Cancelled Cheque',
    why: 'Proof of active bank account with IFSC and MICR details',
    accepts: ['CANCELLED_CHEQUE', 'BANK_STATEMENT_SUMMARY', 'KRA_KYC_LETTER'],
    unlocks: ['bank_account_verified'],
  },
  link_upi_penny_drop: {
    action_id: 'link_upi_penny_drop',
    kind: 'FORM',
    title: 'Verify Bank via Penny Drop',
    why: 'Instant automated ₹1 test credit verification',
    input_schema: [
      {
        key: 'upi_id',
        type: 'text',
        label: 'UPI ID / VPA for Penny Drop Verification',
        required: true,
        placeholder: 'e.g. user@paytm',
      },
    ],
    unlocks: ['bank_account_verified'],
  },
  register_enach_mandate: {
    action_id: 'register_enach_mandate',
    kind: 'FORM',
    title: 'Set Up Recurring SIP Mandate',
    why: 'NPCI eNACH digital mandate for automatic monthly debits',
    input_schema: [
      {
        key: 'bank_account_number',
        type: 'text',
        label: 'Bank Account Number for eNACH Mandate',
        required: true,
        placeholder: 'e.g. 123456789012',
      },
      {
        key: 'ifsc_code',
        type: 'text',
        label: 'Bank IFSC Code',
        required: true,
        placeholder: 'e.g. HDFC0001234',
      },
      {
        key: 'max_debit_limit',
        type: 'money',
        label: 'Maximum Debit Limit (₹)',
        required: true,
        min: 500,
        max: 1000000,
        placeholder: 'e.g. 50000',
      },
    ],
    unlocks: ['sip_mandate_approved'],
  },
  sign_investment_declaration: {
    action_id: 'sign_investment_declaration',
    kind: 'FORM',
    title: 'Sign Regulatory Declarations',
    why: 'Accept SEBI investment terms and confirm FATCA/CRS status',
    input_schema: [
      {
        key: 'accept_sebi_declarations',
        type: 'boolean',
        label: 'I confirm Indian tax residency (FATCA/CRS) and accept SEBI mutual fund scheme terms',
        required: true,
      },
    ],
    unlocks: ['nomination_and_fatca_signed'],
  },
};

export function getActionDefinition(actionId: string | undefined): ActionOption | undefined {
  if (!actionId) return undefined;
  return ACTION_CATALOG[actionId] || ACTION_CATALOG[actionId.toLowerCase()] || ACTION_CATALOG[actionId.toUpperCase()];
}
