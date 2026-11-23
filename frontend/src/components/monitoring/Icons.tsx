import React from 'react';

const shapes = {
    terrarium: <><path d="M4 8h16v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zM3 5h18M7 8V5m10 3V5"/><path d="M7 17c4-4 6 2 10-2M12 16c0-4 1-6 4-6 0 3-1 5-4 5"/></>,
    back: <><path d="m10 5-7 7 7 7M4 12h16"/></>,
    refresh: <><path d="M20 7v5h-5"/><path d="M19.4 10A7.8 7.8 0 1 0 18 17"/></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 10h18"/></>,
    left: <path d="m14 6-6 6 6 6"/>,
    right: <path d="m10 6 6 6-6 6"/>,
    plus: <path d="M12 5v14M5 12h14"/>,
    minus: <path d="M5 12h14"/>,
    temperature: <><path d="M9 14.3V5a3 3 0 0 1 6 0v9.3a5 5 0 1 1-6 0z"/><path d="M12 8v9"/><circle cx="12" cy="18" r="1"/></>,
    humidity: <><path d="M12 2S5 10 5 15a7 7 0 0 0 14 0c0-5-7-13-7-13z"/><path d="M8.5 15a3.5 3.5 0 0 0 3.5 3.5"/></>,
    connection: <><path d="M2 8.5a16 16 0 0 1 20 0M5 12a11 11 0 0 1 14 0m-11 3.4a6.8 6.8 0 0 1 8 0"/><circle cx="12" cy="19" r="1"/></>,
    archive: <><rect x="3" y="4" width="18" height="5" rx="1.5"/><path d="M5 9v11h14V9m-9 4h4"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/></>,
    alert: <><path d="M10.4 4.5a1.9 1.9 0 0 1 3.2 0l8 13.6a1.9 1.9 0 0 1-1.6 2.9H4a1.9 1.9 0 0 1-1.6-2.9zM12 9v4"/><circle cx="12" cy="16.8" r=".5"/></>,
};

export type IconName = keyof typeof shapes;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
    return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]}</svg>;
}
