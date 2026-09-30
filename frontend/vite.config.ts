/// <reference types="vitest" />
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// Deployment traceability: Vercel sets VERCEL_GIT_COMMIT_SHA at build time.
// Hex-only so an unexpected value can never inject markup.
const buildCommit = (process.env.VERCEL_GIT_COMMIT_SHA ?? process.env.GIT_SHA ?? '').replace(
  /[^0-9a-f]/gi,
  ''
) || 'dev';

const buildCommitMeta: Plugin = {
  name: 'build-commit-meta',
  transformIndexHtml: (html) =>
    html.replace('</head>', `  <meta name="app-commit" content="${buildCommit}" />\n  </head>`),
};

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), buildCommitMeta],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/tests/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}', 'tests/unit/**/*.{test,spec}.{ts,tsx}'],
  },
});
