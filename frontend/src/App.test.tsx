import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';

describe('App Root Suite', () => {
  it('renders application shell and home screen by default', () => {
    render(<App />);
    expect(screen.getByTestId('app-shell')).toBeInTheDocument();
    expect(screen.getByTestId('screen-01-home')).toBeInTheDocument();
  });
});
