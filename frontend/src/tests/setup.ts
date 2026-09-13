import '@testing-library/jest-dom';
import { beforeAll, afterEach, afterAll } from 'vitest';
import { server } from '../mocks/server';
import { resetMockState } from '../mocks/handlers';
import { setOverrideScenario } from '../mocks/scenarios';

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

afterEach(() => {
  server.resetHandlers();
  resetMockState();
  setOverrideScenario(null);
});

afterAll(() => {
  server.close();
});
