export interface Gauge {
    min: number | null;
    avg: number | null;
    max: number | null;
    count: number;
}

export interface Runtime {
    on: number;
    off: number;
    unknown: number;
}

export interface Summary {
    temperature: Gauge;
    humidity: Gauge;
    online: number;
    recovered: number;
    unknown: number;
    power: Runtime;
    led: Runtime;
    cooling: Runtime;
}

export interface Bucket extends Summary {
    start: number;
    end: number;
}

export interface TimeRange {
    start: number;
    end: number;
}

export interface History extends TimeRange {
    step: number;
    earliest: number | null;
    latest: number | null;
    buckets: Bucket[];
    summary: Summary;
}

export const MINUTE = 60;
export const DAY = 86400;
export const MAX_SPAN = 5 * 365 * DAY;

export function latestMinute() {
    return Math.floor(Date.now() / (1000 * MINUTE)) * MINUTE;
}

export function windowEndingAt(end: number, span: number): TimeRange {
    const width = Math.min(MAX_SPAN, Math.max(MINUTE, Math.round(span / MINUTE) * MINUTE));
    const right = Math.max(width, Math.min(latestMinute(), Math.round(end / MINUTE) * MINUTE));
    return { start: right - width, end: right };
}

export function duration(minutes: number) {
    if (!minutes) return '0 min';
    const days = Math.floor(minutes / 1440);
    const hours = Math.floor(minutes % 1440 / 60);
    const remainder = minutes % 60;
    if (days) return [days + 'd', hours ? hours + 'h' : '', remainder ? remainder + 'm' : ''].filter(Boolean).join(' ');
    if (hours) return hours + 'h' + (remainder ? ' ' + remainder + 'm' : '');
    return minutes + ' min';
}

export function formatPercent(part: number, total: number) {
    if (!total) return '—';
    return (100 * part / total).toLocaleString(undefined, { maximumFractionDigits: 1 });
}

export async function loadHistory(range: TimeRange, authorization: string, signal: AbortSignal, onUnauthorized?: () => void): Promise<History> {
    const query = new URLSearchParams({
        start: String(range.start),
        end: String(range.end),
        points: '480',
    });
    const response = await fetch('/terra/api/monitoring/history?' + query, {
        headers: { Authorization: authorization, Accept: 'application/json' },
        credentials: 'omit',
        cache: 'no-store',
        signal,
    });
    if (response.status === 401 || response.status === 403) {
        if (!signal.aborted) onUnauthorized?.();
        throw new Error('Your sign-in does not grant access to monitoring history.');
    }
    if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) {
        throw new Error('The history service is unavailable. Try the request again.');
    }
    const history = await response.json() as History;
    if (!history.summary || !Array.isArray(history.buckets) || history.start !== range.start || history.end !== range.end) {
        throw new Error('The history service returned an incomplete time range.');
    }
    return history;
}
