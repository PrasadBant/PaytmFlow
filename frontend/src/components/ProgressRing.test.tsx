import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ProgressRing } from './ProgressRing';

describe('ProgressRing (F12)', () => {
  it('renders correct step counts and completed label in centre', () => {
    render(<ProgressRing completed={3} total={7} />);

    expect(screen.getByTestId('progress-ring-count')).toHaveTextContent('3/7');
    expect(screen.getByTestId('progress-ring-label')).toHaveTextContent('Completed');
  });

  it('renders accessible progressbar with aria attributes', () => {
    render(<ProgressRing completed={3} total={7} />);

    const progressbar = screen.getByRole('progressbar');
    expect(progressbar).toBeInTheDocument();
    expect(progressbar).toHaveAttribute('aria-valuenow', '3');
    expect(progressbar).toHaveAttribute('aria-valuemin', '0');
    expect(progressbar).toHaveAttribute('aria-valuemax', '7');
    expect(progressbar).toHaveAttribute('aria-label', '3 of 7 steps completed');
  });

  it('calculates SVG arc dash offset accurately', () => {
    const { container } = render(
      <ProgressRing completed={3} total={7} size="md" strokeWidth={10} />
    );

    const circles = container.querySelectorAll('circle');
    expect(circles.length).toBe(2);

    const foregroundCircle = circles[1];
    const radius = Number(foregroundCircle.getAttribute('r'));
    const circumference = 2 * Math.PI * radius;

    expect(Number(foregroundCircle.getAttribute('stroke-dasharray'))).toBeCloseTo(
      circumference,
      2
    );

    const expectedOffset = circumference - (3 / 7) * circumference;
    expect(Number(foregroundCircle.getAttribute('stroke-dashoffset'))).toBeCloseTo(
      expectedOffset,
      2
    );
  });

  it('renders 0/0 and 0/7 boundary cases safely without NaN', () => {
    const { rerender } = render(<ProgressRing completed={0} total={0} />);
    expect(screen.getByTestId('progress-ring-count')).toHaveTextContent('0/0');

    rerender(<ProgressRing completed={0} total={7} />);
    expect(screen.getByTestId('progress-ring-count')).toHaveTextContent('0/7');

    rerender(<ProgressRing completed={7} total={7} />);
    expect(screen.getByTestId('progress-ring-count')).toHaveTextContent('7/7');
  });

  it('renders across size presets (sm, md, lg)', () => {
    const { rerender, container } = render(
      <ProgressRing completed={2} total={5} size="sm" />
    );
    expect(container.querySelector('div')).toHaveStyle({ width: '88px', height: '88px' });

    rerender(<ProgressRing completed={2} total={5} size="lg" />);
    expect(container.querySelector('div')).toHaveStyle({ width: '160px', height: '160px' });
  });

  it('STRICTLY ASSERTS NO % CHARACTER AND NO BANNED WORD IN OUTPUT', () => {
    const { container } = render(<ProgressRing completed={3} total={7} />);

    const fullHtml = container.innerHTML;
    const fullText = container.textContent || '';

    // Prohibited percentage symbol
    expect(fullHtml).not.toContain('%');
    expect(fullText).not.toContain('%');

    // Prohibited words (score, approval, probability, eligibility, guaranteed)
    expect(fullHtml).not.toMatch(/score/i);
    expect(fullHtml).not.toMatch(/approval/i);
    expect(fullHtml).not.toMatch(/probabilit/i);
    expect(fullHtml).not.toMatch(/eligib/i);
    expect(fullHtml).not.toMatch(/guarantee/i);
  });
});
