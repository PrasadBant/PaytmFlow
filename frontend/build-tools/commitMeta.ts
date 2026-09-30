import type { Plugin } from 'vite';

/**
 * Deployment traceability: the commit a build came from, for
 * <meta name="app-commit">. Vercel sets VERCEL_GIT_COMMIT_SHA at build time
 * (when system environment variables are exposed); GIT_SHA is a manual
 * override. Only a hex hash is ever emitted, so no env value can inject
 * markup. Without metadata a production build says "unknown", never "dev".
 */
export function resolveBuildCommit(
  env: Record<string, string | undefined>,
  command: 'build' | 'serve'
): string {
  const raw = (env.VERCEL_GIT_COMMIT_SHA || env.GIT_SHA || '').trim().toLowerCase();
  if (/^[0-9a-f]{7,40}$/.test(raw)) return raw;
  return command === 'build' ? 'unknown' : 'dev';
}

export function buildCommitMeta(env: Record<string, string | undefined> = process.env): Plugin {
  let commit = 'dev';
  return {
    name: 'build-commit-meta',
    configResolved(config) {
      commit = resolveBuildCommit(env, config.command);
    },
    transformIndexHtml: (html) =>
      html.replace('</head>', `  <meta name="app-commit" content="${commit}" />\n  </head>`),
  };
}
