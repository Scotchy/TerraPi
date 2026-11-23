import React, { useMemo, useState } from 'react';
import { Bucket, duration, Gauge, History } from './history';
import './charts.css';

type Sensor = 'temperature' | 'humidity';
type Track = 'connection' | 'power' | 'led' | 'cooling';
type Chart = 'climate' | 'equipment';
type State = 'online' | 'on' | 'off' | 'recovered' | 'unknown';
type StateDuration = { state: State; minutes: number };

const sensors: Sensor[] = ['temperature', 'humidity'];
const sensorNames = { temperature: 'Temperature', humidity: 'Humidity' };
const tracks: Track[] = ['connection', 'power', 'led', 'cooling'];
const trackNames = { connection: 'Connection', power: 'Terrarium power', led: 'LED lights', cooling: 'Cooling system' };
const stateNames = { online: 'Online', on: 'On', off: 'Off', recovered: 'Recovered', unknown: 'Unknown' };
const dateTime = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const clockTime = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });

function fraction(time: number, history: History) {
    return Math.max(0, Math.min(1, (time - history.start) / (history.end - history.start)));
}

function durations(bucket: Bucket, track: Track): StateDuration[] {
    if (track === 'connection') {
        return [
            { state: 'online', minutes: bucket.online },
            { state: 'recovered', minutes: bucket.recovered },
            { state: 'unknown', minutes: bucket.unknown },
        ];
    }
    return [
        { state: 'on', minutes: bucket[track].on },
        { state: 'off', minutes: bucket[track].off },
        { state: 'unknown', minutes: bucket[track].unknown },
    ];
}

function periodLabel(bucket: Bucket) {
    const start = new Date(bucket.start * 1000);
    const end = new Date(bucket.end * 1000);
    const endFormat = start.toDateString() === end.toDateString() ? clockTime : dateTime;
    return dateTime.format(start) + ' – ' + endFormat.format(end);
}

const TimeAxis = React.memo(function TimeAxis({ history }: { history: History }) {
    const span = history.end - history.start;
    const formatter = new Intl.DateTimeFormat(undefined, span < 240
        ? { hour: '2-digit', minute: '2-digit', second: '2-digit' }
        : span <= 86400 ? { hour: '2-digit', minute: '2-digit' }
        : span <= 86400 * 4 ? { month: 'short', day: 'numeric', hour: '2-digit' }
        : span <= 86400 * 365 ? { month: 'short', day: 'numeric' } : { month: 'short', year: '2-digit' });
    return <div className="tc-time-axis" aria-hidden="true">
        {[0, 1, 2, 3, 4].map(index => <span key={index} style={{ left: (index * 25) + '%' }}>
            {formatter.format((history.start + span * index / 4) * 1000)}
        </span>)}
    </div>;
});

function sensorScale(buckets: Bucket[], sensor: Sensor) {
    let low = Infinity, high = -Infinity;
    for (const bucket of buckets) {
        const value = bucket[sensor];
        if (value.min !== null && value.max !== null) {
            low = Math.min(low, value.min);
            high = Math.max(high, value.max);
        }
    }
    if (!Number.isFinite(low)) return sensor === 'temperature' ? [0, 40] : [0, 100];
    // Give flat signals a readable scale, then round the grid to four equal intervals.
    const span = Math.max(high - low, sensor === 'temperature' ? 2 : 8) * 1.15;
    const magnitude = Math.pow(10, Math.floor(Math.log10(span / 4)));
    const step = ([1, 2, 2.5, 5, 10].find(n => n * magnitude >= span / 4) || 10) * magnitude;
    let min = Math.floor(((low + high) / 2 - step * 2) / step) * step;
    if (min + step * 4 < high) min += step;
    if (sensor === 'humidity' && low >= 0 && high <= 100) {
        if (step * 4 >= 100) return [0, 100];
        min = Math.min(100 - step * 4, Math.max(0, min));
    }
    return [min, min + step * 4];
}

function tickLabel(value: number) {
    return Number(value.toFixed(2)).toString();
}

type Point = { x: number; avg: number; min: number; max: number };

function signalGeometry(history: History, sensor: Sensor, scale: number[]) {
    const groups: Point[][] = [];
    let group: Point[] = [];
    let previousEnd: number | undefined;
    const y = (value: number) => 100 * (scale[1] - value) / (scale[1] - scale[0]);
    const flush = () => {
        if (group.length) groups.push(group);
        group = [];
    };
    for (const bucket of history.buckets) {
        const value = bucket[sensor];
        // A partly missing aggregate cannot establish continuity with its neighbours.
        const incomplete = value.count < (bucket.end - bucket.start) / 60;
        if (bucket.start !== previousEnd || incomplete) flush();
        previousEnd = bucket.end;
        if (value.avg === null || value.max === null || value.min === null) {
            flush();
            continue;
        }
        group.push({
            x: fraction((bucket.start + bucket.end) / 2, history) * 1000,
            avg: y(value.avg), min: y(value.min), max: y(value.max),
        });
        if (incomplete) flush();
    }
    flush();
    const bands: string[] = [], lines: string[] = [], dots: string[] = [], whiskers: string[] = [];
    const coords = (point: Point, key: 'min' | 'max' | 'avg') => point.x.toFixed(2) + ',' + point[key].toFixed(2);
    for (const points of groups) {
        if (points.length === 1) {
            const point = points[0];
            dots.push('M' + coords(point, 'avg') + 'h0.001');
            whiskers.push('M' + coords(point, 'min') + 'L' + coords(point, 'max'));
        } else {
            lines.push('M' + points.map(p => coords(p, 'avg')).join('L'));
            bands.push('M' + points.map(p => coords(p, 'max')).join('L') + 'L' +
                points.slice().reverse().map(p => coords(p, 'min')).join('L') + 'Z');
        }
    }
    return { bands: bands.join(''), lines: lines.join(''), dots: dots.join(''), whiskers: whiskers.join('') };
}

function Signal({ history, sensor, scale }: { history: History; sensor: Sensor; scale: number[] }) {
    const geometry = useMemo(() => signalGeometry(history, sensor, scale), [history, sensor, scale]);
    return <g className={'tc-' + sensor}>
        <path d={geometry.bands} fill="currentColor" fillOpacity=".13" />
        <path d={geometry.whiskers} fill="none" stroke="currentColor" strokeOpacity=".5" vectorEffect="non-scaling-stroke" />
        <path d={geometry.lines} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        <path d={geometry.dots} fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </g>;
}

function trackPaths(history: History, track: Track) {
    const paths: Partial<Record<State, string[]>> = {};
    for (const bucket of history.buckets) {
        const values = durations(bucket, track);
        const total = values.reduce((sum, value) => sum + value.minutes, 0);
        const start = (fraction(bucket.start, history) * 1000).toFixed(3);
        const end = (fraction(bucket.end, history) * 1000).toFixed(3);
        let top = 0;
        // Slice the height by duration; only the horizontal dimension conveys time.
        for (const value of values) {
            if (!value.minutes) continue;
            const bottom = top + 100 * value.minutes / total;
            const segments = paths[value.state] || [];
            segments.push('M' + start + ',' + top.toFixed(2) + 'H' + end + 'V' + bottom.toFixed(2) + 'H' + start + 'Z');
            paths[value.state] = segments;
            top = bottom;
        }
    }
    return paths;
}

const StateBar = React.memo(function StateBar({ history, track }: { history: History; track: Track }) {
    const paths = useMemo(() => trackPaths(history, track), [history, track]);
    return <div className="tc-state-track">
        <span className="tc-track-label">{trackNames[track]}</span>
        <svg viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">
            {(Object.keys(paths) as State[]).map(state =>
                <path key={state} className={'tc-state-' + state} d={paths[state]!.join('')} />)}
        </svg>
    </div>;
});

function valueText(value: Gauge, sensor: Sensor) {
    const unit = sensor === 'temperature' ? ' °C' : '%';
    return value.avg === null ? 'No reading' : value.avg.toFixed(1) + unit;
}

function binDetails(bucket: Bucket, chart: Chart) {
    if (chart === 'climate') return sensors.map(sensor => {
        const gauge = bucket[sensor];
        const label = gauge.min !== null && gauge.max !== null && gauge.min !== gauge.max
            ? tickLabel(gauge.min) + '–' + tickLabel(gauge.max) + (sensor === 'temperature' ? ' °C' : '%')
            : '';
        return { name: sensorNames[sensor], value: valueText(gauge, sensor), detail: label };
    });
    return tracks.map(track => ({
        name: trackNames[track],
        value: durations(bucket, track).filter(s => s.minutes > 0)
            .map(s => stateNames[s.state] + ' ' + duration(s.minutes)).join(' · ') || 'No data',
        detail: '',
    }));
}

function chartIndex(history: History, position: number) {
    const time = history.start + position * (history.end - history.start);
    let low = 0, high = history.buckets.length - 1;
    while (low < high) {
        const mid = Math.floor((low + high) / 2);
        if (time >= history.buckets[mid].end) low = mid + 1;
        else high = mid;
    }
    return low;
}

interface ChartsProps {
    history: History;
    onZoom: (start: number, end: number) => void;
}

export function MonitoringCharts({ history, onZoom }: ChartsProps) {
    const [visible, setVisible] = useState({ temperature: true, humidity: true });
    const [inspection, setInspection] = useState<{ chart: Chart; index: number } | null>(null);
    const [drag, setDrag] = useState<{ chart: Chart; from: number; to: number } | null>(null);
    const scales = useMemo(() => ({
        temperature: sensorScale(history.buckets, 'temperature'),
        humidity: sensorScale(history.buckets, 'humidity'),
    }), [history]);
    const hasReadings = useMemo(() => sensors.some(sensor => visible[sensor] &&
        history.buckets.some(bucket => bucket[sensor].avg !== null)), [history, visible]);
    const bucket = inspection && history.buckets[inspection.index];
    const cursor = bucket ? fraction((bucket.start + bucket.end) / 2, history) : null;
    const timeAt = (pos: number) => Math.round(history.start + (history.end - history.start) * pos);
    const atPointer = (event: React.PointerEvent<HTMLDivElement>) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        return Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
    };
    const moveTo = (chart: Chart, pos: number) => {
        const index = chartIndex(history, pos);
        setInspection(previous => previous?.chart === chart && previous.index === index ? previous : { chart, index });
    };

    function bindChart(chart: Chart) {
        const index = inspection?.chart === chart ? inspection.index : 0;
        const activeBucket = history.buckets[index];
        return {
            tabIndex: history.buckets.length ? 0 : -1, role: 'slider',
            'aria-label': chart === 'climate' ? 'Inspect climate history' : 'Inspect equipment history',
            'aria-describedby': 'tc-instructions-' + chart,
            'aria-valuemin': 0, 'aria-valuemax': Math.max(0, history.buckets.length - 1),
            'aria-valuenow': Math.min(index, Math.max(0, history.buckets.length - 1)),
            'aria-valuetext': activeBucket
                ? periodLabel(activeBucket) + '. ' + binDetails(activeBucket, chart).map(d => d.name + ' ' + d.value + (d.detail ? ', range ' + d.detail : '')).join('. ')
                : 'No observations',
            onFocus: () => setInspection({ chart, index: 0 }),
            onBlur: () => { setInspection(null); setDrag(null); },
            onPointerMove: (event: React.PointerEvent<HTMLDivElement>) => {
                if (!event.isPrimary) return;
                const pos = atPointer(event);
                moveTo(chart, pos);
                if (drag?.chart === chart) setDrag({ ...drag, to: pos });
            },
            onPointerLeave: () => { if (!drag) setInspection(null); },
            onPointerDown: (event: React.PointerEvent<HTMLDivElement>) => {
                if (!event.isPrimary || event.button !== 0) return;
                event.currentTarget.focus();
                event.currentTarget.setPointerCapture(event.pointerId);
                const pos = atPointer(event);
                setDrag({ chart, from: pos, to: pos });
                moveTo(chart, pos);
            },
            onPointerUp: (event: React.PointerEvent<HTMLDivElement>) => {
                if (!drag || !event.isPrimary) return;
                const pos = atPointer(event);
                const distance = Math.abs(pos - drag.from) * event.currentTarget.clientWidth;
                setDrag(null);
                if (distance < 8) return;
                const start = timeAt(Math.min(drag.from, pos));
                const end = timeAt(Math.max(drag.from, pos));
                if (end > start) {
                    setInspection(null);
                    onZoom(start, end);
                }
            },
            onPointerCancel: () => { setDrag(null); setInspection(null); },
            onKeyDown: (event: React.KeyboardEvent<HTMLDivElement>) => {
                const last = history.buckets.length - 1;
                const increment = event.shiftKey ? 10 : 1;
                const targets: Record<string, number> = {
                    ArrowLeft: index - increment, ArrowRight: index + increment, Home: 0, End: last,
                };
                if (event.key === 'Escape') {
                    setInspection(null);
                    setDrag(null);
                } else if (event.key in targets && last >= 0) {
                    event.preventDefault();
                    setInspection({ chart, index: Math.max(0, Math.min(last, targets[event.key])) });
                }
            },
        };
    }

    function overlay(chart: Chart) {
        const showTip = !drag && cursor !== null && inspection?.chart === chart && bucket;
        return <>
            {cursor !== null && <div className="tc-cursor" style={{ left: cursor * 100 + '%' }} />}
            {drag && <div className="tc-selection" style={{
                left: Math.min(drag.from, drag.to) * 100 + '%', width: Math.abs(drag.from - drag.to) * 100 + '%',
            }} />}
            {showTip && bucket && <div className={'tc-tooltip tc-tooltip-' + (cursor! > 0.5 ? 'left' : 'right')} aria-hidden="true">
                <strong>{periodLabel(bucket)}</strong>
                {binDetails(bucket, chart).map(detail => <div key={detail.name}>
                    <span>{detail.name}</span>
                    <b>{detail.value}{detail.detail && <small>{detail.detail}</small>}</b>
                </div>)}
            </div>}
        </>;
    }

    return <div className="tc-charts">
        <section className="tc-panel" aria-labelledby="tc-climate-title">
            <div className="tc-heading">
                <h2 id="tc-climate-title">Climate history</h2>
                <div className="tc-series-controls">
                    {sensors.map(sensor => <button type="button" key={sensor}
                        className={'tc-series-key tc-' + sensor} aria-pressed={visible[sensor]}
                        aria-label={'Show ' + sensorNames[sensor].toLowerCase() + ' series'}
                        disabled={visible[sensor] && !visible[sensor === 'temperature' ? 'humidity' : 'temperature']}
                        onClick={() => setVisible({ ...visible, [sensor]: !visible[sensor] })}>
                        <i aria-hidden="true" />{sensorNames[sensor]}
                    </button>)}
                </div>
            </div>
            <div className="tc-climate-body">
                <div className="tc-axis-headings" aria-hidden="true"><span className="tc-temperature">°C</span><span className="tc-humidity">% RH</span></div>
                <div className="tc-plot-margin">
                    <div className="tc-plot tc-surface" {...bindChart('climate')}>
                        {[0, 1, 2, 3, 4].map(i => <div key={i} className="tc-grid-row" style={{ top: i * 25 + '%' }} aria-hidden="true">
                            {sensors.map(sensor => <span className={'tc-axis tc-' + sensor} key={sensor}>
                                {visible[sensor] && tickLabel(scales[sensor][1] + i / 4 * (scales[sensor][0] - scales[sensor][1]))}
                            </span>)}
                        </div>)}
                        <svg viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">
                            {sensors.map(sensor => visible[sensor] && <Signal key={sensor} history={history} scale={scales[sensor]} sensor={sensor} />)}
                        </svg>
                        {!hasReadings && <div className="tc-empty">No climate readings in this period</div>}
                        {overlay('climate')}
                    </div>
                    <TimeAxis history={history} />
                </div>
            </div>
            <div className="tc-footer" id="tc-instructions-climate">
                <span>Lines show averages. Shading shows the measured range.</span>
                <span>Drag to zoom · Use ← → to inspect</span>
            </div>
        </section>
        <section className="tc-panel" aria-labelledby="tc-equipment-title">
            <div className="tc-heading"><h2 id="tc-equipment-title">Connection &amp; equipment</h2></div>
            <div className="tc-equipment-body">
                <div className="tc-plot-margin">
                    <div className="tc-states tc-surface" {...bindChart('equipment')}>
                        {tracks.map(track => <StateBar key={track} history={history} track={track} />)}
                        {overlay('equipment')}
                    </div>
                    <TimeAxis history={history} />
                </div>
            </div>
            <div className="tc-footer tc-track-footer">
                <div className="tc-state-legend">
                    <span><i className="tc-state-on" />Online / on</span>
                    <span><i className="tc-state-off" />Off</span>
                    <span><i className="tc-state-recovered" />Offline · recovered</span>
                    <span><i className="tc-state-unknown" />Unknown / no data</span>
                </div>
                <span id="tc-instructions-equipment">Stacked colors show time spent in each state. Use ← → to inspect.</span>
            </div>
        </section>
    </div>;
}
