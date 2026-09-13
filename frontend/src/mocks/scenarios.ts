export type MockScenario =
  | 'normal'
  | 'stale'
  | 'invalid'
  | 'needsreview'
  | 'deadend'
  | 'aitimeout'
  | 'empty'
  | 'slow';

let overrideScenario: MockScenario | null = null;

export function getActiveScenario(requestUrl?: string, request?: Request): MockScenario {
  if (overrideScenario) {
    return overrideScenario;
  }

  // Check URL query parameters in browser or incoming request
  try {
    const urlStr = requestUrl || (typeof window !== 'undefined' ? window.location.href : '');
    if (urlStr) {
      const url = new URL(urlStr, 'http://localhost');
      const param = url.searchParams.get('scenario');
      if (param && isValidScenario(param)) {
        return param;
      }
    }
  } catch {
    // Fall back to referer / sessionStorage / default
  }

  // Check referer header (sent by browser fetch when on page with ?scenario=...)
  if (request) {
    try {
      const referer = request.headers.get('referer');
      if (referer) {
        const refUrl = new URL(referer, 'http://localhost');
        const param = refUrl.searchParams.get('scenario');
        if (param && isValidScenario(param)) {
          return param;
        }
      }
      const headerScenario = request.headers.get('x-scenario');
      if (headerScenario && isValidScenario(headerScenario)) {
        return headerScenario;
      }
    } catch {
      // Fall back to sessionStorage / default
    }
  }

  if (typeof window !== 'undefined' && window.sessionStorage) {
    const stored = window.sessionStorage.getItem('pf_mock_scenario');
    if (stored && isValidScenario(stored)) {
      return stored as MockScenario;
    }
  }

  return 'normal';
}

export function setOverrideScenario(scenario: MockScenario | null): void {
  overrideScenario = scenario;
  if (typeof window !== 'undefined' && window.sessionStorage) {
    if (scenario) {
      window.sessionStorage.setItem('pf_mock_scenario', scenario);
    } else {
      window.sessionStorage.removeItem('pf_mock_scenario');
    }
  }
}

function isValidScenario(value: string): value is MockScenario {
  return ['normal', 'stale', 'invalid', 'needsreview', 'deadend', 'aitimeout', 'empty', 'slow'].includes(value);
}
