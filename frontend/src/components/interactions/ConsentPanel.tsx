import { useState, type ReactElement } from 'react';
import { FileCheck2, FileText, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/primitives/Button';
import { Modal } from '@/components/primitives/Modal';

export interface ConsentPanelProps {
  actionTitle: string;
  why?: string | null;
  fieldKey?: string | null;
  submitLabel: string;
  isSubmitting?: boolean;
  actionId?: string | null;
  journeyType?: string | null;
  goal?: unknown;
  fields?: unknown;
  onSubmit: (values: Record<string, unknown>) => void | Promise<void>;
}

export function ConsentPanel({
  actionTitle,
  why,
  fieldKey,
  submitLabel,
  isSubmitting = false,
  actionId,
  journeyType,
  goal,
  fields,
  onSubmit,
}: ConsentPanelProps): ReactElement {
  const [agreed, setAgreed] = useState(false);
  const [showAgreementModal, setShowAgreementModal] = useState(false);

  // Dynamic Loan Terms calculations for Lending journey
  const isLendingAgreement =
    actionId === 'ACCEPT_LOAN_TERMS' ||
    actionId === 'accept_loan_agreement' ||
    journeyType === 'LENDING' ||
    actionTitle.toLowerCase().includes('loan agreement') ||
    actionTitle.toLowerCase().includes('loan terms');

  // Extract from state / goal / fields dynamically
  let rawAmount: number | undefined;
  let rawTenure: number | undefined;

  if (Array.isArray(fields)) {
    for (const f of fields as Array<{ key?: string; value?: unknown; display_value?: string }>) {
      if (f && (f.key === 'requested_amount' || f.key === 'loan_amount' || f.key === 'amount')) {
        const val = typeof f.value === 'number' ? f.value : Number(String(f.display_value || f.value || '').replace(/[^0-9.]/g, ''));
        if (!isNaN(val) && val > 0) rawAmount = val;
      }
      if (f && (f.key === 'loan_tenure_months' || f.key === 'tenure_months' || f.key === 'tenure')) {
        const val = typeof f.value === 'number' ? f.value : Number(String(f.display_value || f.value || '').replace(/[^0-9.]/g, ''));
        if (!isNaN(val) && val > 0) rawTenure = val;
      }
    }
  } else if (fields && typeof fields === 'object') {
    const fObj = fields as Record<string, unknown>;
    if (typeof fObj.requested_amount === 'number') rawAmount = fObj.requested_amount;
    else if (typeof fObj.loan_amount === 'number') rawAmount = fObj.loan_amount;
    if (typeof fObj.loan_tenure_months === 'number') rawTenure = fObj.loan_tenure_months;
    else if (typeof fObj.tenure_months === 'number') rawTenure = fObj.tenure_months;
  }

  if (!rawAmount && goal && typeof goal === 'object') {
    const gObj = goal as Record<string, unknown>;
    if (typeof gObj.requested_amount === 'number') rawAmount = gObj.requested_amount;
    else if (typeof gObj.loan_amount === 'number') rawAmount = gObj.loan_amount;
    if (typeof gObj.loan_tenure_months === 'number') rawTenure = gObj.loan_tenure_months;
    else if (typeof gObj.tenure_months === 'number') rawTenure = gObj.tenure_months;
  }

  const loanAmount = rawAmount || 200000;
  const tenureMonths = rawTenure || 24;
  
  const interestRatePa = 10.5; // 10.5% p.a.
  const monthlyRate = interestRatePa / 12 / 100;
  const emi = Math.round(
    (loanAmount * monthlyRate * Math.pow(1 + monthlyRate, tenureMonths)) /
      (Math.pow(1 + monthlyRate, tenureMonths) - 1)
  );
  const processingFee = Math.round(loanAmount * 0.015 * 1.18); // 1.5% + 18% GST
  const totalRepayment = emi * tenureMonths + processingFee;

  return (
    <div data-testid="consent-panel" className="space-y-6">
      {/* Action Header */}
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-full bg-paytm-blue-50 text-paytm-blue flex items-center justify-center shrink-0">
          <FileCheck2 className="w-5 h-5" />
        </div>
        <div className="space-y-1">
          <h2 className="text-base font-semibold text-content-primary">{actionTitle}</h2>
          <p className="text-xs text-content-secondary leading-relaxed">
            {why || 'Review and confirm to proceed.'}
          </p>
        </div>
      </div>

      {/* Dynamic Key Loan Terms Summary for Lending Flow */}
      {isLendingAgreement && (
        <div
          data-testid="loan-terms-summary"
          className="p-5 rounded-card border border-paytm-blue/20 bg-gradient-to-br from-blue-50/50 to-white space-y-4"
        >
          <div className="flex items-center justify-between border-b border-surface-border pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-paytm-blue" />
              <span className="text-xs font-bold uppercase tracking-wider text-paytm-blue">
                Key Loan Sanction Terms
              </span>
            </div>
            <span className="text-xs text-content-tertiary">Pre-Approved Offer</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-content-secondary">Loan Amount</div>
              <div className="text-sm font-bold text-content-primary mt-0.5" data-testid="loan-term-amount">
                ₹{loanAmount.toLocaleString('en-IN')}
              </div>
            </div>
            <div>
              <div className="text-xs text-content-secondary">Tenure</div>
              <div className="text-sm font-bold text-content-primary mt-0.5" data-testid="loan-term-tenure">
                {tenureMonths} months
              </div>
            </div>
            <div>
              <div className="text-xs text-content-secondary">Interest Rate</div>
              <div className="text-sm font-bold text-content-primary mt-0.5" data-testid="loan-term-rate">
                {interestRatePa}% p.a.
              </div>
            </div>
            <div>
              <div className="text-xs text-content-secondary">Monthly Repayment (EMI)</div>
              <div className="text-sm font-bold text-paytm-blue mt-0.5" data-testid="loan-term-emi">
                ₹{emi.toLocaleString('en-IN')}
              </div>
            </div>
            <div>
              <div className="text-xs text-content-secondary">Processing Fee</div>
              <div className="text-sm font-bold text-content-primary mt-0.5" data-testid="loan-term-fee">
                ₹{processingFee.toLocaleString('en-IN')}
              </div>
            </div>
            <div>
              <div className="text-xs text-content-secondary">Total Repayment</div>
              <div className="text-sm font-bold text-content-primary mt-0.5" data-testid="loan-term-total">
                ₹{totalRepayment.toLocaleString('en-IN')}
              </div>
            </div>
          </div>

          {/* View Full Loan Agreement Action */}
          <div className="pt-2 border-t border-surface-border/60">
            <button
              type="button"
              onClick={() => setShowAgreementModal(true)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-paytm-blue hover:text-paytm-blue-action transition-colors cursor-pointer"
              data-testid="view-full-agreement-btn"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>View full loan agreement →</span>
            </button>
          </div>
        </div>
      )}

      {/* Acknowledgement Checkbox */}
      <label className="flex items-start gap-3 p-4 rounded-card border border-surface-border bg-surface-subtle cursor-pointer hover:bg-slate-50 transition-colors">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-0.5 w-4 h-4 accent-paytm-blue shrink-0 cursor-pointer"
          data-testid="consent-checkbox"
        />
        <span className="text-sm text-content-primary leading-relaxed">
          {isLendingAgreement
            ? 'I have read, understood, and accept the Key Loan Terms, Repayment Schedule, and the Full Loan Agreement.'
            : 'I have read and agree to the above terms and conditions.'}
        </span>
      </label>

      {/* Submit Button */}
      <Button
        type="button"
        variant="primary"
        size="lg"
        className="w-full font-semibold shadow-xs"
        disabled={!agreed || isSubmitting}
        isLoading={isSubmitting}
        onClick={() => void onSubmit({ [fieldKey || 'accept_terms']: true })}
        data-testid="consent-confirm-btn"
      >
        {submitLabel}
      </Button>

      {/* Full Agreement Modal */}
      {showAgreementModal && (
        <Modal
          isOpen={showAgreementModal}
          onClose={() => setShowAgreementModal(false)}
          title="Personal Loan Agreement & Sanction Terms"
          size="lg"
        >
          <div className="space-y-5 text-content-primary text-xs leading-relaxed max-h-[60vh] overflow-y-auto pr-2" data-testid="full-loan-agreement-modal">
            <div className="p-4 rounded-card bg-surface-subtle border border-surface-border space-y-2">
              <div className="font-bold text-sm text-content-primary">Schedule of Loan Terms</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><strong>Sanctioned Amount:</strong> ₹{loanAmount.toLocaleString('en-IN')}</div>
                <div><strong>Tenure:</strong> {tenureMonths} Months</div>
                <div><strong>Annual Interest Rate:</strong> {interestRatePa}% p.a. (Fixed)</div>
                <div><strong>Monthly EMI:</strong> ₹{emi.toLocaleString('en-IN')}</div>
                <div><strong>Processing Charges:</strong> ₹{processingFee.toLocaleString('en-IN')} (inc. GST)</div>
                <div><strong>Repayment Mode:</strong> eNACH / Auto-Debit Mandate</div>
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="font-bold text-content-primary">1. Disbursement & Utilization</h4>
              <p className="text-content-secondary">
                The Lender agrees to disburse the sanctioned amount to the Borrower&apos;s verified bank account upon execution of this agreement and successful verification of auto-debit mandate.
              </p>
            </div>

            <div className="space-y-2">
              <h4 className="font-bold text-content-primary">2. Repayment Schedule & Mode</h4>
              <p className="text-content-secondary">
                The Borrower agrees to pay the monthly installment of ₹{emi.toLocaleString('en-IN')} on or before the 5th of every calendar month for a period of {tenureMonths} consecutive months.
              </p>
            </div>

            <div className="space-y-2">
              <h4 className="font-bold text-content-primary">3. Prepayment & Foreclosure Charges</h4>
              <p className="text-content-secondary">
                Zero foreclosure charges after completion of 6 successful EMI payments in compliance with applicable RBI Fair Practices Code.
              </p>
            </div>

            <div className="space-y-2">
              <h4 className="font-bold text-content-primary">4. Borrower Undertaking & Consent</h4>
              <p className="text-content-secondary">
                The Borrower certifies that all documents and information provided during this journey are accurate and genuine, and agrees to the digital execution of this agreement.
              </p>
            </div>

            <div className="pt-4 border-t border-surface-border flex justify-end">
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setAgreed(true);
                  setShowAgreementModal(false);
                }}
              >
                Acknowledge & Close
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default ConsentPanel;

