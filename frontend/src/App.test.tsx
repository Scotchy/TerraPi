import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import Paho from 'paho-mqtt';
import App from './App';
import { TextEncoder } from 'util';
import { SettingsModal } from './components/SettingsModal';

jest.mock('paho-mqtt', () => ({ Client: jest.fn() }));

const config = {
  revision: 'original', current_mode: 'day', log_interval: 5,
  sensors: { canopy: { type: 'DHT22' } }, controls: { light: { type: 'Relay' } },
  modes: { day: { light: true }, night: { light: false } },
  planning: { active: true, default_mode: 'day', periods: {} }
};

const broker = {
  clientId: 'request', connect: jest.fn(), disconnect: jest.fn(), subscribe: jest.fn(), send: jest.fn(),
  isConnected: jest.fn(), onMessageArrived: (_: Partial<Paho.Message>) => {},
  onConnectionLost: () => {}
};

function receive(destinationName: string, value: unknown) {
  act(() => broker.onMessageArrived({ destinationName, payloadString: typeof value === 'string' ? value : JSON.stringify(value) }));
}

function login() {
  render(<App />);
  fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'fixture' } });
  fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'synthetic' } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));
  act(() => broker.connect.mock.calls[0][0].onSuccess());
}

beforeEach(() => {
  global.TextEncoder = TextEncoder as typeof global.TextEncoder;
  jest.clearAllMocks();
  (Paho.Client as jest.Mock).mockImplementation(() => broker);
  broker.isConnected.mockReturnValue(true);
});

test('removes old credentials and prompts for MQTT login', () => {
  document.cookie = 'password=legacy; path=/';
  localStorage.setItem('terrapi_biometric_pass', 'legacy');
  render(<App />);
  expect(document.cookie).not.toContain('password=');
  expect(localStorage.getItem('terrapi_biometric_pass')).toBeNull();
  expect(screen.getByRole('button', { name: 'Sign In' })).toBeDisabled();
  expect(Paho.Client).not.toHaveBeenCalled();
});

test('tracks the configured sensor, server planning state, stale data and reconnect', () => {
  jest.useFakeTimers();
  try {
    login();
    receive('config/full', config);
    receive('sensor/canopy/temperature', '24');
    expect(screen.getByText('24°C')).toBeInTheDocument();
    const planning = screen.getByLabelText('Planning');
    fireEvent.click(planning);
    expect(planning).toBeChecked();
    receive('config/full', { ...config, planning: { ...config.planning, active: false } });
    receive('config/status', { request_id: 'request-1', success: true });
    expect(planning).not.toBeChecked();
    act(() => { jest.advanceTimersByTime(16000); });
    expect(screen.queryByText('24°C')).toBeNull();
    expect(screen.getByTitle('Settings')).toBeDisabled();
    act(() => broker.onConnectionLost());
    expect(screen.getByText(/Broker disconnected/)).toBeInTheDocument();
    act(() => broker.connect.mock.calls[0][0].onSuccess());
    expect(broker.send).toHaveBeenCalledWith('config/get', '1', 0, false);
    receive('config/full', config);
    expect(screen.getByTitle('Settings')).toBeEnabled();
    expect(document.cookie).not.toContain('password=');
  } finally {
    jest.useRealTimers();
  }
});

test('saves a rename and its schedule together and waits for the matching response', async () => {
  login();
  receive('config/full', config);
  fireEvent.click(screen.getByTitle('Settings'));
  fireEvent.blur(screen.getByLabelText('Rename mode day'), { target: { value: 'daytime' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
  const calls = broker.send.mock.calls.filter(([topic]) => topic === 'config/update');
  const update = JSON.parse(calls[0][1]);
  expect(update.revision).toBe('original');
  expect(update.data.planning.default_mode).toBe('daytime');
  expect(Object.keys(update.data.modes)).toEqual(['night', 'daytime']);
  receive('config/status', { request_id: 'another-user', success: true });
  expect(screen.getByText('Save Changes')).toBeDisabled();
  await act(async () => receive('config/status', { request_id: update.request_id, success: false, message: 'Conflict' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Conflict');
  receive('config/full', { ...config, revision: 'elsewhere' });
  expect(screen.getByDisplayValue('daytime')).toBeInTheDocument();
  fireEvent.click(screen.getByText('Discard draft and reload'));
  expect(screen.queryByDisplayValue('daytime')).toBeNull();
});

test('loads a late settings snapshot and rejects duplicate mode and period names', () => {
  const snapshot = { ...config, planning: { ...config.planning, periods: {
    sunrise: { start: '07:00', end: '09:00', mode: 'day' },
    evening: { start: '17:00', end: '21:00', mode: 'night' }
  } } };
  const props = { visible: true, online: true, onSave: jest.fn(), onClose: jest.fn() };
  const modal = render(<SettingsModal {...props} config={null} />);
  modal.rerender(<SettingsModal {...props} config={snapshot} />);
  fireEvent.blur(screen.getByLabelText('Rename mode day'), { target: { value: 'night' } });
  expect(screen.getByLabelText('Rename mode day')).toHaveValue('day');
  expect(screen.getByLabelText('Rename mode night')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Planning' }));
  fireEvent.blur(screen.getByLabelText('Rename period sunrise'), { target: { value: 'evening' } });
  expect(screen.getByLabelText('Rename period sunrise')).toHaveValue('sunrise');
  expect(screen.getByLabelText('Rename period evening')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save Changes' })).toBeDisabled();
});

test('a monitoring bookmark authenticates directly with the history service', async () => {
  const fetch = global.fetch;
  try {
    global.fetch = jest.fn().mockResolvedValue({ status: 401 });
    window.history.replaceState(null, '', '/terra/#monitoring');
    render(<App />);
    fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'fixture' } });
    fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'expired' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));
    expect(await screen.findByText('Could not sign in. Check the connection and credentials.')).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/terra/api/monitoring/history?'),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Basic ' + btoa('fixture:expired') }) }));
    expect(Paho.Client).not.toHaveBeenCalled();
  } finally {
    global.fetch = fetch;
    window.history.replaceState(null, '', '/');
  }
});
