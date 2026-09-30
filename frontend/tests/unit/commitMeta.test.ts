import { describe, expect, it } from 'vitest';
import { resolveBuildCommit } from '../../build-tools/commitMeta';

const SHA = '4189f19a72dde628433103d2ce52629252c280e5';

describe('resolveBuildCommit', () => {
  it('uses the Vercel commit for a production build', () => {
    expect(resolveBuildCommit({ VERCEL_GIT_COMMIT_SHA: SHA }, 'build')).toBe(SHA);
  });

  it('prefers the Vercel commit over a manual GIT_SHA and normalises case', () => {
    expect(
      resolveBuildCommit({ VERCEL_GIT_COMMIT_SHA: SHA.toUpperCase(), GIT_SHA: 'abc1234' }, 'build')
    ).toBe(SHA);
    expect(resolveBuildCommit({ GIT_SHA: 'abc1234' }, 'build')).toBe('abc1234');
  });

  it('says "unknown", never "dev", for a production build without metadata', () => {
    expect(resolveBuildCommit({}, 'build')).toBe('unknown');
    expect(resolveBuildCommit({ VERCEL_GIT_COMMIT_SHA: '' }, 'build')).toBe('unknown');
  });

  it('keeps "dev" for the local dev server', () => {
    expect(resolveBuildCommit({}, 'serve')).toBe('dev');
  });

  it('never emits a non-hash value', () => {
    for (const bad of ['"><script>alert(1)</script>', 'main', '/vercel/path0', 'abc']) {
      expect(resolveBuildCommit({ VERCEL_GIT_COMMIT_SHA: bad }, 'build')).toBe('unknown');
    }
  });
});
