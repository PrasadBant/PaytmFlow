import type React from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/primitives/Card';
import { Spinner } from '@/components/primitives/Spinner';
import { IndianRupee, Shield, CreditCard, IdCard, Landmark, LineChart, AlertCircle } from 'lucide-react';
import { usePacks } from '@/api/hooks/usePacks';
import type { JourneyPackSummary } from '@/api/hooks/usePacks';

const IconMap: Record<string, React.FC<{ className?: string }>> = {
  rupee: IndianRupee,
  shield: Shield,
  card: CreditCard,
  id: IdCard,
  bank: Landmark,
  chart: LineChart,
};

export const Screen02JourneySelection: React.FC = () => {
  const { data, isLoading, isError, error } = usePacks();
  const packs = data?.packs;
  const navigate = useNavigate();

  return (
    <div data-testid="screen-02-journey-selection" className="p-6 max-w-page mx-auto pb-12">
      <div className="flex flex-col items-center text-center space-y-2 mb-10 mt-6">
        <h1 className="text-3xl md:text-4xl font-bold text-content-primary tracking-tight">
          Choose Your Financial Journey
        </h1>
        <p className="text-content-secondary">
          Select the journey you want to continue or start.
        </p>
      </div>

      {isLoading && (
        <div className="flex flex-col items-center justify-center p-12 text-content-secondary">
          <Spinner size="lg" className="mb-4" />
          <p>Loading journeys...</p>
        </div>
      )}

      {isError && (
        <div className="flex flex-col items-center justify-center p-12 text-paytm-red bg-paytm-red-light rounded-card border border-red-200">
          <AlertCircle className="w-10 h-10 mb-4" />
          <p className="font-semibold mb-1">Failed to load journeys</p>
          <p className="text-sm">{error instanceof Error ? error.message : 'Unknown error occurred'}</p>
        </div>
      )}

      {packs && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 md:gap-6 max-w-3xl mx-auto">
          {packs.map((pack: JourneyPackSummary) => {
            const Icon = IconMap[pack.icon] || AlertCircle;
            const isDraft = pack.lifecycle_status === 'DRAFT';
            const isFlagship = pack.flagship_demo || pack.journey_type === 'LENDING';

            // Clean concise title matching reference
            const referenceTitle =
              pack.journey_type === 'LENDING'
                ? 'Loan / Lending'
                : pack.journey_type === 'INSURANCE'
                ? 'Insurance'
                : pack.journey_type === 'CREDIT_CARD'
                ? 'Credit Card'
                : pack.journey_type === 'KYC'
                ? 'KYC / Onboarding'
                : pack.journey_type === 'ACCOUNT_OPENING'
                ? 'Account Opening'
                : pack.journey_type === 'INVESTMENT'
                ? 'Investment / Wealth'
                : pack.display_name;

            const referenceDescription =
              pack.journey_type === 'LENDING'
                ? 'Complete your loan application'
                : pack.journey_type === 'INSURANCE'
                ? 'Resume or complete your insurance application'
                : pack.journey_type === 'CREDIT_CARD'
                ? 'Finish your credit card application'
                : pack.journey_type === 'KYC'
                ? 'Complete your KYC verification'
                : pack.journey_type === 'ACCOUNT_OPENING'
                ? 'Resume your account opening journey'
                : pack.journey_type === 'INVESTMENT'
                ? 'Complete your investment onboarding'
                : pack.description;

            return (
              <Card
                key={pack.journey_type}
                variant="default"
                hoverEffect={!isDraft}
                className={`flex flex-col items-center text-center p-6 md:p-8 rounded-card transition-all cursor-pointer ${
                  isFlagship
                    ? 'border-2 border-paytm-blue-action bg-white shadow-card ring-2 ring-paytm-blue-50'
                    : 'border border-surface-border bg-white shadow-xs hover:border-slate-300'
                } ${isDraft ? 'opacity-50 cursor-not-allowed bg-surface-muted' : ''}`}
                onClick={() => {
                  if (!isDraft) {
                    navigate(`/start/${pack.journey_type}`);
                  }
                }}
                title={isDraft ? 'This journey is coming soon' : undefined}
                data-testid={`pack-card-${pack.journey_type}`}
              >
                <div className="h-14 w-14 rounded-full bg-blue-50 text-paytm-blue flex items-center justify-center mb-3.5">
                  <Icon className="h-7 w-7" aria-hidden="true" />
                </div>
                
                <h2 className="font-bold text-lg text-content-primary mb-1">
                  {referenceTitle}
                  {pack.display_name && pack.display_name !== referenceTitle && (
                    <span className="sr-only"> {pack.display_name}</span>
                  )}
                </h2>
                
                <p className="text-xs sm:text-sm text-content-secondary mb-3 max-w-xs">
                  {referenceDescription}
                  {pack.description && pack.description !== referenceDescription && (
                    <span className="sr-only"> {pack.description}</span>
                  )}
                </p>

                {isFlagship && (
                  <div className="mt-auto pt-1">
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-paytm-blue-50 text-paytm-blue-action border border-paytm-blue-action/20">
                      Flagship Demo
                    </span>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
