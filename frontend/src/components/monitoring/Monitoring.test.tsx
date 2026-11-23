import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import Monitoring from './Monitoring';
import { DAY, History } from './history';

const now = Date.UTC(2026, 7, 10, 12);
const authorization = 'Basic test';
const originalFetch = global.fetch;

function historyResponse(url: string, temperature: number) {
    const query = new URL(url, 'http://localhost').searchParams;
    const start = Number(query.get('start'));
    const end = Number(query.get('end'));
    const minutes = (end - start) / 60;
    const state = { on: minutes, off: 0, unknown: 0 };
    const summary = {
        temperature: { avg: temperature, min: temperature, max: temperature, count: 1 },
        humidity: { avg: null, min: null, max: null, count: 0 },
        online: minutes, recovered: 0, unknown: 0, power: state, led: state, cooling: state,
    };
    const history: History = { start, end, step: end - start, earliest: start, latest: end - 60, buckets: [{ start, end, ...summary }], summary };
    return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => history } as unknown as Response;
}

beforeEach(() => { jest.spyOn(Date, 'now').mockReturnValue(now); });
afterEach(() => { global.fetch = originalFetch; jest.restoreAllMocks(); });

test('requests the selected period with dashboard credentials and ignores a late response for an earlier selection', async () => {
    let resolveFirst: (response: Response) => void = () => {};
    const fetchHistory = jest.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { resolveFirst = resolve; }))
        .mockImplementation((url: string) => Promise.resolve(historyResponse(url, 23)));
    global.fetch = fetchHistory;
    render(<Monitoring onBack={() => {}} authorization={authorization} />);
    const [firstUrl, firstOptions] = fetchHistory.mock.calls[0];
    expect(firstUrl).toContain('start=' + (now / 1000 - DAY));
    expect(firstOptions.headers.Authorization).toBe(authorization);
    expect(firstOptions.credentials).toBe('omit');

    fireEvent.click(screen.getByRole('button', { name: '7d' }));
    expect(firstOptions.signal.aborted).toBe(true);
    expect(await screen.findByText('23.0')).toBeInTheDocument();
    await act(async () => resolveFirst(historyResponse(firstUrl, 99)));
    expect(screen.queryByText('99.0')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Previous period' }));
    await screen.findByText('23.0');
    const previous = new URL(fetchHistory.mock.calls[2][0], 'http://localhost');
    expect(Number(previous.searchParams.get('end'))).toBe(now / 1000 - 7 * DAY);
    expect(screen.getByRole('button', { name: 'Follow latest' })).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    await screen.findByText('23.0');
    const zoom = new URL(fetchHistory.mock.calls[3][0], 'http://localhost');
    expect(Number(zoom.searchParams.get('end')) - Number(zoom.searchParams.get('start'))).toBe(7 * DAY / 2);
});

test('reports history-service failure and retries the selected custom interval', async () => {
    const fetchHistory = jest.fn().mockResolvedValue({ ok: false, status: 503 })
        .mockImplementationOnce((url: string) => Promise.resolve(historyResponse(url, 20)));
    global.fetch = fetchHistory;
    render(<Monitoring onBack={() => {}} authorization={authorization} />);
    await screen.findByText('20.0');
    fireEvent.click(screen.getByRole('button', { name: 'Custom' }));
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-10T09:00' } });
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-01-10T10:30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply range' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('history service is unavailable');
    expect(screen.queryByText('20.0')).toBeNull();
    fetchHistory.mockImplementationOnce((url: string) => Promise.resolve(historyResponse(url, 18)));
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('18.0')).toBeInTheDocument();
    expect(fetchHistory.mock.calls[2][0]).toEqual(fetchHistory.mock.calls[1][0]);
    const selected = new URL(fetchHistory.mock.calls[2][0], 'http://localhost');
    expect(Number(selected.searchParams.get('end')) - Number(selected.searchParams.get('start'))).toBe(90 * 60);
});
