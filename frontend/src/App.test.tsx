import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';

describe('App Root Suite', () => {
  it('renders application shell and home screen by default', async () => {
    render(<App />);
    expect(await screen.findByTestId('app-shell')).toBeInTheDocument();
    expect(screen.getByTestId('screen-01-home')).toBeInTheDocument();
  });
});
