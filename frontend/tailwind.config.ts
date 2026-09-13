import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        paytm: {
          blue: {
            DEFAULT: 'var(--pf-color-paytm-blue)',
            action: 'var(--pf-color-paytm-blue-action)',
            'action-hover': 'var(--pf-color-paytm-blue-action-hover)',
            50: 'var(--pf-color-paytm-blue-50)',
            100: 'var(--pf-color-paytm-blue-100)',
            600: 'var(--pf-color-paytm-blue-600)',
            700: 'var(--pf-color-paytm-blue-700)',
            dark: 'var(--pf-color-paytm-blue-700)',
          },
          cyan: {
            DEFAULT: 'var(--pf-color-paytm-cyan)',
            light: 'var(--pf-color-paytm-cyan-light)',
          },
          green: {
            DEFAULT: 'var(--pf-color-paytm-green)',
            light: 'var(--pf-color-paytm-green-light)',
            dark: 'var(--pf-color-paytm-green-dark)',
          },
          amber: {
            DEFAULT: 'var(--pf-color-paytm-amber)',
            light: 'var(--pf-color-paytm-amber-light)',
            dark: 'var(--pf-color-paytm-amber-dark)',
          },
          red: {
            DEFAULT: 'var(--pf-color-paytm-red)',
            light: 'var(--pf-color-paytm-red-light)',
            dark: 'var(--pf-color-paytm-red-dark)',
          },
        },
        surface: {
          DEFAULT: 'var(--pf-color-surface)',
          muted: 'var(--pf-color-surface-muted)',
          subtle: 'var(--pf-color-surface-subtle)',
          border: 'var(--pf-color-surface-border)',
          hover: 'var(--pf-color-surface-hover)',
        },
        content: {
          primary: 'var(--pf-color-content-primary)',
          secondary: 'var(--pf-color-content-secondary)',
          tertiary: 'var(--pf-color-content-tertiary)',
          inverted: 'var(--pf-color-content-inverted)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
      width: {
        sidebar: 'var(--pf-width-sidebar)',
      },
      height: {
        header: 'var(--pf-height-header)',
      },
      maxWidth: {
        page: 'var(--pf-max-width-page)',
      },
      borderRadius: {
        card: 'var(--pf-radius-lg)',
        button: 'var(--pf-radius-md)',
        badge: 'var(--pf-radius-full)',
      },
      boxShadow: {
        card: '0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        'card-hover': '0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -1px rgba(0, 0, 0, 0.04)',
        modal: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
      },
    },
  },
  plugins: [],
} satisfies Config;
