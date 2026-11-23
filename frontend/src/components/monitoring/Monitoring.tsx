import React, { useEffect, useRef, useState } from 'react';
import { MonitoringCharts } from './Charts';
import { Icon, IconName } from './Icons';
import { DAY, duration, formatPercent, Gauge, History, latestMinute, loadHistory, MAX_SPAN, MINUTE, Summary, TimeRange, windowEndingAt } from './history';
import './monitoring.css';

const periods = [
    { label: '1h', seconds: 3600 }, { label: '6h', seconds: 21600 },
    { label: '24h', seconds: DAY }, { label: '7d', seconds: 7 * DAY },
    { label: '30d', seconds: 30 * DAY }, { label: '1y', seconds: 365 * DAY },
];
const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const dateTime = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const clockTime = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });

function rangeLabel({ start, end }: TimeRange) {
    const from = new Date(start * 1000);
    const to = new Date(end * 1000);
    const sameDay = from.toDateString() === to.toDateString();
    return dateTime.format(from) + ' – ' + (sameDay ? clockTime : dateTime).format(to);
}

function dateInput(timestamp: number) {
    const date = new Date(timestamp * 1000);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function RangeForm({ range, apply, close }: { range: TimeRange; apply: (range: TimeRange) => void; close: () => void }) {
    const [start, setStart] = useState(dateInput(range.start));
    const [end, setEnd] = useState(dateInput(range.end));
    const [error, setError] = useState('');
    const input = useRef<HTMLInputElement>(null);
    useEffect(() => { input.current?.focus(); }, []);
    return <form id="monitor-custom-range" className="mon-custom" onKeyDown={event => {
        if (event.key === 'Escape') close();
    }} onSubmit={event => {
        event.preventDefault();
        const from = new Date(start).getTime() / 1000;
        const to = new Date(end).getTime() / 1000;
        if (!Number.isFinite(from) || !Number.isFinite(to) || from < 0 || to > latestMinute() || from >= to) {
            setError('Choose an end after the start and up to the last complete minute.');
        } else if (to - from > MAX_SPAN) {
            setError('Choose a period of 1,825 days or less.');
        } else {
            apply({ start: from, end: to });
        }
    }}>
        <label>From<input type="datetime-local" ref={input} value={start} max={dateInput(latestMinute())} required onChange={event => setStart(event.target.value)} /></label>
        <label>To<input type="datetime-local" value={end} max={dateInput(latestMinute())} required onChange={event => setEnd(event.target.value)} /></label>
        <div className="mon-form-actions"><button className="mon-primary" type="submit">Apply range</button><button className="mon-plain" type="button" onClick={close}>Cancel</button></div>
        {error && <div role="alert" className="mon-field-error">{error}</div>}
    </form>;
}

function Metric({ title, icon, value, unit, detail }: { title: string; icon: IconName; value: string; unit?: string; detail: string }) {
    return <div className={'mon-metric mon-metric-' + icon}>
        <div className="mon-metric-head"><h2>{title}</h2><span className="mon-metric-icon"><Icon name={icon} size={17} /></span></div>
        <div className="mon-metric-value">{value}{unit && value !== '—' && <span>{unit}</span>}</div>
        <p>{detail}</p>
    </div>;
}

function reading(value: number | null | undefined) {
    return value == null ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 });
}

function extremes(metric: Gauge | undefined, unit: string) {
    return !metric || metric.min == null || metric.max == null ? 'No readings in this period' :
        [reading(metric.min) + unit + ' low', reading(metric.max) + unit + ' high'].join('  ·  ');
}

function Statistics({ summary }: { summary: Summary }) {
    const total = summary.online + summary.recovered + summary.unknown;
    return <section className="mon-metrics" aria-label="Selected period statistics">
        <Metric title="Mean temperature" icon="temperature" value={reading(summary.temperature.avg)} unit="°C" detail={extremes(summary.temperature, '°C')} />
        <Metric title="Mean humidity" icon="humidity" value={reading(summary.humidity.avg)} unit="%" detail={extremes(summary.humidity, '%')} />
        <Metric title="Time online" icon="connection" value={formatPercent(summary.online, total)} unit="%" detail={duration(summary.online) + ' connected'} />
        <Metric title="Recorded coverage" icon="archive" value={formatPercent(summary.online + summary.recovered, total)} unit="%" detail={duration(summary.recovered) + ' recovered after reconnect'} />
    </section>;
}

function Equipment({ summary }: { summary: Summary }) {
    const rows = [
        { name: 'Terrarium power', data: summary.power },
        { name: 'LED lights', data: summary.led },
        { name: 'Cooling system', data: summary.cooling },
    ];
    return <section className="mon-runtime" aria-labelledby="mon-runtime-title">
        <h2 id="mon-runtime-title">Equipment runtime</h2>
        <p className="mon-runtime-note">Durations are estimated from one-minute samples. Terrarium power follows the controller’s operating mode. A missing report leaves power unknown.</p>
        <div className="mon-table-scroll">
            <table>
                <thead><tr><th scope="col">Equipment</th><th scope="col">On</th><th scope="col">Off</th><th scope="col">Unknown</th><th scope="col">On during known time</th></tr></thead>
                <tbody>{rows.map(({ name, data }) => <tr key={name}>
                    <th scope="row">{name}</th><td>{duration(data.on)}</td><td>{duration(data.off)}</td><td>{duration(data.unknown)}</td>
                    <td>{data.on + data.off ? formatPercent(data.on, data.on + data.off) + '%' : '—'}</td>
                </tr>)}</tbody>
            </table>
        </div>
    </section>;
}

interface MonitoringProps {
    authorization: string;
    onBack: () => void;
    onUnauthorized?: () => void;
}

function Monitoring({ authorization, onBack, onUnauthorized }: MonitoringProps) {
    const [range, setRange] = useState(() => windowEndingAt(latestMinute(), DAY));
    const [following, setFollowing] = useState(true);
    const [custom, setCustom] = useState(false);
    const [retry, setRetry] = useState(0);
    const [loaded, setLoaded] = useState<History | null>(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);
    const customButton = useRef<HTMLButtonElement>(null);
    const title = useRef<HTMLHeadingElement>(null);
    const span = range.end - range.start;

    useEffect(() => { title.current?.focus(); }, []);
    useEffect(() => {
        if (!following) return;
        const advance = () => {
            if (document.hidden) return;
            const end = latestMinute();
            setRange(previous => previous.end === end ? previous : windowEndingAt(end, previous.end - previous.start));
        };
        const interval = window.setInterval(advance, 15000);
        document.addEventListener('visibilitychange', advance);
        return () => {
            window.clearInterval(interval);
            document.removeEventListener('visibilitychange', advance);
        };
    }, [following]);

    useEffect(() => {
        const controller = new AbortController();
        setLoading(true);
        setError('');
        loadHistory(range, authorization, controller.signal, onUnauthorized).then(history => {
            if (!controller.signal.aborted) {
                setLoaded(history);
                setLoading(false);
            }
        }).catch((reason: Error) => {
            if (!controller.signal.aborted) {
                setError(reason instanceof TypeError ? 'The history service could not be reached. Check the connection and try again.' : reason.message);
                setLoading(false);
            }
        });
        return () => controller.abort();
    }, [range, authorization, retry, onUnauthorized]);

    const matchesRange = loaded && loaded.start === range.start && loaded.end === range.end;
    const previousLiveMinute = loaded && following && loaded.end - loaded.start === span && range.end - loaded.end === MINUTE;
    const display = matchesRange || previousLiveMinute ? loaded : null;

    function browse(next: TimeRange) {
        setFollowing(false);
        setRange(windowEndingAt(next.end, next.end - next.start));
    }
    function zoom(factor: number) {
        const width = Math.max(MINUTE, Math.min(MAX_SPAN, Math.round(span * factor / MINUTE) * MINUTE));
        const nextEnd = following ? latestMinute() : (range.start + range.end + width) / 2;
        setRange(windowEndingAt(nextEnd, width));
    }
    function closeCustom() {
        setCustom(false);
        customButton.current?.focus();
    }
    function follow() {
        if (!following) setRange(windowEndingAt(latestMinute(), span));
        setFollowing(!following);
    }

    return <div className="monitor-page">
        <header className="mon-topbar"><div className="mon-topbar-content">
            <div className="mon-brand"><span className="mon-brand-icon"><Icon name="terrarium" size={23} /></span>TerraPi</div>
            <button className="mon-back" onClick={onBack}><Icon name="back" size={16} />Live controls</button>
        </div></header>

        <main className="mon-content">
            <div className="mon-page-head">
                <div><h1 ref={title} tabIndex={-1}>Terrarium monitoring</h1>
                    <p className="mon-range-label"><Icon name="clock" size={15} /><span>{rangeLabel(display || range)} <span className="mon-zone">({localZone})</span></span></p>
                </div>
                <button className="mon-follow" aria-pressed={following} onClick={follow} title="Move the selected window forward each minute">
                    <span className="mon-switch" aria-hidden="true"><span /></span>Follow latest
                </button>
            </div>

            <section className="mon-toolbar" aria-label="Time window">
                <div className="mon-toolbar-row">
                    <div className="mon-periods" role="group" aria-label="Period">
                        <span className="mon-period-label"><Icon name="calendar" size={16} />Period</span>
                        {periods.map(period => <button key={period.label} aria-pressed={!custom && span === period.seconds} onClick={() => {
                            setCustom(false);
                            setRange(windowEndingAt(following ? latestMinute() : range.end, period.seconds));
                        }}>{period.label}</button>)}
                        <button ref={customButton} className={custom || !periods.some(period => period.seconds === span) ? 'mon-custom-active' : ''} aria-expanded={custom} onClick={() => setCustom(!custom)}>Custom</button>
                    </div>
                    <div className="mon-navigation" role="group" aria-label="Navigate chart">
                        <button onClick={() => browse(windowEndingAt(range.start, span))} disabled={range.start <= 0} aria-label="Previous period" title="Previous period"><Icon name="left" /></button>
                        <button onClick={() => browse(windowEndingAt(range.end + span, span))} disabled={range.end >= latestMinute()} aria-label="Next period" title="Next period"><Icon name="right" /></button>
                        <span className="mon-tool-divider" />
                        <button onClick={() => zoom(0.5)} disabled={span <= MINUTE} aria-label="Zoom in" title="Zoom in"><Icon name="plus" /></button>
                        <button onClick={() => zoom(2)} disabled={span >= MAX_SPAN} aria-label="Zoom out" title="Zoom out"><Icon name="minus" /></button>
                        <span className="mon-tool-divider" />
                        <button onClick={() => setRetry(value => value + 1)} disabled={loading} aria-label="Refresh this period" title="Refresh this period"><Icon name="refresh" /></button>
                    </div>
                </div>
                {custom && <RangeForm range={range} close={closeCustom} apply={next => { browse(next); closeCustom(); }} />}
            </section>

            {error && <div className="mon-notice mon-error" role="alert"><Icon name="alert" /><span>{error}</span><button className="mon-plain" onClick={() => setRetry(value => value + 1)}>Retry</button></div>}
            {!display && loading && <div role="status" className="mon-notice"><span className="mon-loader" />Loading monitoring history…</div>}
            {display && <>
                <Statistics summary={display.summary} />
                {display.earliest === null && <p className="mon-notice">Waiting for the first terrarium record. History will appear once the controller reports.</p>}
                <MonitoringCharts history={display} onZoom={(start, end) => browse(windowEndingAt(end, end - start))} />
                <Equipment summary={display.summary} />
                <footer className="mon-foot">
                    {display.earliest !== null && <span>First retained record <strong>{dateTime.format(display.earliest * 1000)}</strong></span>}
                    {display.latest !== null && <span>Last record <strong>{dateTime.format(display.latest * 1000)}</strong></span>}
                    <span>Chart interval <strong>{duration(display.step / MINUTE)}</strong></span>
                </footer>
            </>}
        </main>
    </div>;
}

export default React.memo(Monitoring);
