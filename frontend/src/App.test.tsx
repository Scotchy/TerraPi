import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';
import { TextEncoder } from 'util';

test('prompts for MQTT login before connecting', () => {
  render(<App />);
  expect(screen.getByRole('button', { name: 'Sign In' })).toBeDisabled();
  expect(screen.getByPlaceholderText('Username')).toBeInTheDocument();
});

test('a monitoring bookmark checks the saved login with the history service', async () => {
  const fetch = global.fetch;
  const encoder = global.TextEncoder;
  const request = jest.fn().mockResolvedValue({ status: 401 });
  try {
    global.fetch = request;
    global.TextEncoder = TextEncoder as typeof global.TextEncoder;
    window.history.replaceState(null, '', '/terra/#monitoring');
    document.cookie = 'username=old-dashboard; path=/';
    document.cookie = 'password=expired; path=/';
    render(<App />);
    expect(await screen.findByText('Sign in with the dashboard account to view history.')).toBeInTheDocument();
    expect(request).toHaveBeenCalledWith(expect.stringContaining('/terra/api/monitoring/history?'),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Basic ' + btoa('old-dashboard:expired') }) }));
  } finally {
    global.fetch = fetch;
    global.TextEncoder = encoder;
    document.cookie = 'username=; path=/; max-age=0';
    document.cookie = 'password=; path=/; max-age=0';
    window.history.replaceState(null, '', '/');
  }
});
