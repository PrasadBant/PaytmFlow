import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

describe('Design Tokens Verification (UI/UX §1-2)', () => {
  it('defines all required CSS token variables in tokens.css', () => {
    const tokensPath = path.resolve(__dirname, 'tokens.css');
    expect(fs.existsSync(tokensPath)).toBe(true);

    const cssContent = fs.readFileSync(tokensPath, 'utf-8');

    // Brand colors
    expect(cssContent).toContain('--pf-color-paytm-blue: #002e6e;');
    expect(cssContent).toContain('--pf-color-paytm-cyan: #00baf2;');
    expect(cssContent).toContain('--pf-color-paytm-green: #00b972;');
    expect(cssContent).toContain('--pf-color-paytm-amber: #ff9900;');
    expect(cssContent).toContain('--pf-color-paytm-red: #e53935;');

    // Surface & Content
    expect(cssContent).toContain('--pf-color-surface: #ffffff;');
    expect(cssContent).toContain('--pf-color-surface-muted: #f8fafc;');
    expect(cssContent).toContain('--pf-color-content-primary: #0f172a;');

    // Layout & Spacing
    expect(cssContent).toContain('--pf-width-sidebar: 260px;');
    expect(cssContent).toContain('--pf-height-header: 64px;');
    expect(cssContent).toContain('--pf-max-width-page: 1200px;');

    // Radii
    expect(cssContent).toContain('--pf-radius-lg: 12px;');
    expect(cssContent).toContain('--pf-radius-md: 8px;');
  });
});
