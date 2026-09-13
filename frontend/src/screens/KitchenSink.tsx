import { useState, type ReactElement } from 'react';
import {
  Button,
  IconButton,
  Card,
  Badge,
  Input,
  MoneyInput,
  Select,
  Tabs,
  Modal,
  Spinner,
} from '@/components/primitives';
import { ArrowRight, Bell, Check, Sparkles, Upload } from 'lucide-react';

export function KitchenSink(): ReactElement {
  const [activeTab, setActiveTab] = useState('buttons');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [moneyValue, setMoneyValue] = useState<number | null>(500000);
  const [textInput, setTextInput] = useState('');
  const [selectVal, setSelectVal] = useState('salaried');

  return (
    <div className="max-w-page mx-auto p-8 space-y-8">
      <div className="border-b border-surface-border pb-4">
        <h1 className="text-2xl font-bold text-content-primary">PaytmFlow Primitives Kitchen Sink</h1>
        <p className="text-sm text-content-secondary mt-1">
          Interactive catalog of all accessible UI primitives and design token variants.
        </p>
      </div>

      <Tabs
        activeTab={activeTab}
        onChange={setActiveTab}
        tabs={[
          { id: 'buttons', label: 'Buttons & Badges' },
          { id: 'forms', label: 'Inputs & Form Controls' },
          { id: 'cards', label: 'Cards & Containers' },
          { id: 'dialogs', label: 'Modals & Spinners' },
        ]}
      />

      {/* Buttons & Badges */}
      {activeTab === 'buttons' && (
        <div className="space-y-6">
          <Card padding="md">
            <h2 className="text-base font-bold text-content-primary mb-4">Button Variants</h2>
            <div className="flex flex-wrap gap-4 items-center">
              <Button variant="primary" rightIcon={<ArrowRight className="w-4 h-4" />}>
                Primary Button
              </Button>
              <Button variant="secondary">Secondary Button</Button>
              <Button variant="cyan" leftIcon={<Sparkles className="w-4 h-4" />}>
                Cyan Action
              </Button>
              <Button variant="outline">Outline Button</Button>
              <Button variant="ghost">Ghost Button</Button>
              <Button variant="danger">Danger Button</Button>
              <Button variant="primary" isLoading>
                Loading State
              </Button>
              <Button variant="primary" disabled>
                Disabled
              </Button>
            </div>
          </Card>

          <Card padding="md">
            <h2 className="text-base font-bold text-content-primary mb-4">Icon Buttons</h2>
            <div className="flex flex-wrap gap-4 items-center">
              <IconButton icon={<Bell className="w-5 h-5" />} aria-label="Notifications" variant="ghost" />
              <IconButton icon={<Upload className="w-5 h-5" />} aria-label="Upload document" variant="primary" />
              <IconButton icon={<Check className="w-5 h-5" />} aria-label="Confirm item" variant="secondary" />
            </div>
          </Card>

          <Card padding="md">
            <h2 className="text-base font-bold text-content-primary mb-4">Badges (Status with Icon Pairing)</h2>
            <div className="flex flex-wrap gap-4 items-center">
              <Badge variant="success">Completed / Satisfied</Badge>
              <Badge variant="warning">Action Required</Badge>
              <Badge variant="amber">Needs Review</Badge>
              <Badge variant="danger">Blocked Item</Badge>
              <Badge variant="info">In Progress</Badge>
              <Badge variant="neutral">Draft</Badge>
              <Badge variant="flagship">Flagship Demo</Badge>
            </div>
          </Card>
        </div>
      )}

      {/* Forms */}
      {activeTab === 'forms' && (
        <Card padding="md" className="space-y-6 max-w-xl">
          <h2 className="text-base font-bold text-content-primary mb-4">Form Controls</h2>

          <Input
            label="Full Legal Name"
            placeholder="e.g. Rahul Sharma"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            helperText="Enter your name exactly as per PAN."
            required
          />

          <Input
            label="Invalid Input Demo"
            placeholder="Invalid value"
            value="bad_value"
            error="This field is required and must be alphanumeric."
            required
          />

          <MoneyInput
            label="Required Loan Amount"
            value={moneyValue ?? undefined}
            onChange={setMoneyValue}
            helperText="Formatted with Indian numbering grouping (e.g. ₹5,00,000)."
            required
          />

          <Select
            label="Employment Status"
            value={selectVal}
            onChange={(e) => setSelectVal(e.target.value)}
            options={[
              { value: 'salaried', label: 'Salaried Professional' },
              { value: 'self_employed_pro', label: 'Self Employed Professional' },
              { value: 'business', label: 'Business Owner' },
            ]}
            required
          />
        </Card>
      )}

      {/* Cards */}
      {activeTab === 'cards' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card variant="default" hoverEffect>
            <h3 className="font-bold text-content-primary">Default Card (Hoverable)</h3>
            <p className="text-sm text-content-secondary mt-1">
              Standard surface card with subtle border and elevation.
            </p>
          </Card>

          <Card variant="tinted-blue">
            <h3 className="font-bold text-paytm-blue">Tinted Blue Card</h3>
            <p className="text-sm text-paytm-blue-700 mt-1">
              Used for AI reasoning explanations and primary highlights.
            </p>
          </Card>

          <Card variant="tinted-amber">
            <h3 className="font-bold text-paytm-amber-dark">Tinted Amber Card</h3>
            <p className="text-sm text-paytm-amber-dark mt-1">
              Used for conflict alerts and needs-review ambiguity cards.
            </p>
          </Card>

          <Card variant="tinted-green">
            <h3 className="font-bold text-paytm-green-dark">Tinted Green Card</h3>
            <p className="text-sm text-paytm-green-dark mt-1">
              Used for verified items and resolved status highlights.
            </p>
          </Card>
        </div>
      )}

      {/* Modals & Spinners */}
      {activeTab === 'dialogs' && (
        <div className="space-y-6">
          <Card padding="md">
            <h2 className="text-base font-bold text-content-primary mb-4">Modal Dialog</h2>
            <Button variant="primary" onClick={() => setIsModalOpen(true)}>
              Open Demo Modal
            </Button>

            <Modal
              isOpen={isModalOpen}
              onClose={() => setIsModalOpen(false)}
              title="Generic Action Modal"
              description="Dynamically rendered modal for FORM actions."
              footer={
                <>
                  <Button variant="ghost" onClick={() => setIsModalOpen(false)}>
                    Cancel
                  </Button>
                  <Button variant="primary" onClick={() => setIsModalOpen(false)}>
                    Submit Action
                  </Button>
                </>
              }
            >
              <div className="space-y-4">
                <p className="text-sm text-content-secondary">
                  Modals have full keyboard focus trap and close on Escape key.
                </p>
                <Input label="Action Parameter" placeholder="Enter detail..." />
              </div>
            </Modal>
          </Card>

          <Card padding="md">
            <h2 className="text-base font-bold text-content-primary mb-4">Spinners</h2>
            <div className="flex items-center gap-6">
              <Spinner size="sm" className="text-paytm-blue" />
              <Spinner size="md" className="text-paytm-cyan" />
              <Spinner size="lg" className="text-paytm-blue" />
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

export default KitchenSink;
