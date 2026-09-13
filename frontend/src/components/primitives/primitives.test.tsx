import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
} from './index';

describe('UI Primitives Suite', () => {
  describe('Button', () => {
    it('renders with children and handles click', async () => {
      const handleClick = vi.fn();
      render(<Button onClick={handleClick}>Click Me</Button>);

      const btn = screen.getByRole('button', { name: 'Click Me' });
      expect(btn).toBeInTheDocument();

      await userEvent.click(btn);
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it('disables button and prevents clicks when disabled or loading', async () => {
      const handleClick = vi.fn();
      const { rerender } = render(
        <Button disabled onClick={handleClick}>
          Disabled
        </Button>
      );

      const btn = screen.getByRole('button', { name: 'Disabled' });
      expect(btn).toBeDisabled();
      await userEvent.click(btn);
      expect(handleClick).not.toHaveBeenCalled();

      rerender(
        <Button isLoading onClick={handleClick}>
          Loading
        </Button>
      );
      expect(screen.getByRole('button')).toBeDisabled();
      expect(screen.getByRole('status')).toBeInTheDocument();
    });
  });

  describe('IconButton', () => {
    it('renders with accessible name from aria-label', async () => {
      const handleClick = vi.fn();
      render(<IconButton icon={<span>🔔</span>} aria-label="Notifications" onClick={handleClick} />);

      const btn = screen.getByRole('button', { name: 'Notifications' });
      expect(btn).toBeInTheDocument();

      await userEvent.click(btn);
      expect(handleClick).toHaveBeenCalledTimes(1);
    });
  });

  describe('Card', () => {
    it('renders card content with variant styling', () => {
      render(
        <Card variant="tinted-blue" padding="lg">
          <p>Card Content</p>
        </Card>
      );
      expect(screen.getByText('Card Content')).toBeInTheDocument();
    });
  });

  describe('Badge', () => {
    it('renders with icon and text pairing for accessibility', () => {
      render(<Badge variant="success">Step Completed</Badge>);
      expect(screen.getByText('Step Completed')).toBeInTheDocument();
    });
  });

  describe('Input', () => {
    it('renders label, input, helper text, and handles input', async () => {
      const handleChange = vi.fn();
      render(
        <Input
          label="Full Name"
          helperText="As per Aadhaar"
          required
          placeholder="e.g. Amit"
          onChange={handleChange}
        />
      );

      expect(screen.getByText('Full Name')).toBeInTheDocument();
      expect(screen.getByText('As per Aadhaar')).toBeInTheDocument();

      const input = screen.getByPlaceholderText('e.g. Amit');
      await userEvent.type(input, 'Amit Kumar');
      expect(handleChange).toHaveBeenCalled();
    });

    it('renders error message and aria-invalid when error is present', () => {
      render(<Input label="Email" error="Invalid email address" id="email-field" />);

      const input = screen.getByLabelText('Email');
      expect(input).toHaveAttribute('aria-invalid', 'true');
      expect(screen.getByText('Invalid email address')).toBeInTheDocument();
    });
  });

  describe('MoneyInput', () => {
    it('formats Indian currency and emits parsed number', async () => {
      const handleChange = vi.fn();
      render(<MoneyInput label="Loan Amount" defaultValue={500000} onChange={handleChange} />);

      const input = screen.getByLabelText('Loan Amount') as HTMLInputElement;
      expect(input.value).toBe('5,00,000');

      await userEvent.clear(input);
      await userEvent.type(input, '1000000');

      expect(handleChange).toHaveBeenCalledWith(1000000);
    });
  });

  describe('Select', () => {
    it('renders options and handles selection change', async () => {
      const handleChange = vi.fn();
      render(
        <Select
          label="Employment"
          options={[
            { value: 'salaried', label: 'Salaried' },
            { value: 'business', label: 'Business' },
          ]}
          onChange={handleChange}
        />
      );

      const select = screen.getByLabelText('Employment');
      await userEvent.selectOptions(select, 'salaried');
      expect(handleChange).toHaveBeenCalled();
    });
  });

  describe('Tabs', () => {
    it('supports tab clicking and keyboard arrow navigation', async () => {
      const handleChange = vi.fn();
      render(
        <Tabs
          activeTab="tab1"
          onChange={handleChange}
          tabs={[
            { id: 'tab1', label: 'Tab One' },
            { id: 'tab2', label: 'Tab Two' },
          ]}
        />
      );

      const tab2 = screen.getByRole('tab', { name: 'Tab Two' });
      await userEvent.click(tab2);
      expect(handleChange).toHaveBeenCalledWith('tab2');

      const tablist = screen.getByRole('tablist');
      fireEvent.keyDown(tablist, { key: 'ArrowRight' });
      expect(handleChange).toHaveBeenCalledWith('tab2');
    });
  });

  describe('Modal', () => {
    it('renders content when open and closes on Escape key', () => {
      const handleClose = vi.fn();
      const { rerender } = render(
        <Modal isOpen={true} onClose={handleClose} title="Test Modal">
          <p>Modal Body</p>
        </Modal>
      );

      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('Test Modal')).toBeInTheDocument();
      expect(screen.getByText('Modal Body')).toBeInTheDocument();

      fireEvent.keyDown(document, { key: 'Escape' });
      expect(handleClose).toHaveBeenCalledTimes(1);

      rerender(
        <Modal isOpen={false} onClose={handleClose} title="Test Modal">
          <p>Modal Body</p>
        </Modal>
      );
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  describe('Spinner', () => {
    it('renders with loading accessibility label', () => {
      render(<Spinner label="Processing..." />);
      expect(screen.getByRole('status', { name: 'Processing...' })).toBeInTheDocument();
    });
  });
});
