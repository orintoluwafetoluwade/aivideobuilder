import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';
describe('AI Video Studio', () => {
  it('renders the creator dashboard', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: /Make something remarkable/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Create new video/i })).toBeInTheDocument();
  });
});
