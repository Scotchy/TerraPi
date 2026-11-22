import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

test('prompts for MQTT login before connecting', () => {
  render(<App />);
  expect(screen.getByRole('button', { name: 'Sign In' })).toBeDisabled();
  expect(screen.getByPlaceholderText('Username')).toBeInTheDocument();
});
