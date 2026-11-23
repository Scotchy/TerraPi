import Paho from 'paho-mqtt';
import React from 'react';
import { Control } from './control';
import { FullConfig, SettingsModal } from './SettingsModal';
import { Toast } from './Toast';
import { LoginModal } from './LoginModal';
import './settings.css';

type Session = 'login' | 'connecting' | 'online' | 'offline';
interface DashboardState {
    session: Session;
    loginError: string;
    config: FullConfig | null;
    currentMode: string;
    controls: Record<string, boolean>;
    readings: Record<string, { value: string; at: number }>;
    contact: number;
    settingsVisible: boolean;
    toast: { visible: boolean; type: 'success' | 'error'; message: string };
}

function initialState(): DashboardState {
    return {
        session: 'login', loginError: '', config: null, currentMode: '', controls: {}, readings: {},
        contact: 0, settingsVisible: false, toast: { visible: false, type: 'success', message: '' }
    };
}

function forgetLegacyCredentials() {
    document.cookie = 'username=; path=/; max-age=0';
    document.cookie = 'password=; path=/; max-age=0';
    for (const key of ['terrapi_credential_id', 'terrapi_biometric_user', 'terrapi_biometric_pass']) {
        localStorage.removeItem(key);
    }
}

export class Terra extends React.Component<{}, DashboardState> {
    state = initialState();
    private client: Paho.Client | null = null;
    private timer?: number;
    private requestNumber = 0;
    private pending?: { id: string; finish: (error?: string) => void };

    componentDidMount() {
        forgetLegacyCredentials();
        if (process.env.NODE_ENV === 'production' && window.location.protocol === 'http:') {
            const secure = new URL(window.location.href);
            secure.protocol = 'https:';
            window.location.replace(secure.href);
        }
        this.timer = window.setInterval(() => {
            if (this.state.session === 'online') this.forceUpdate();
        }, 1000);
    }

    componentWillUnmount() {
        window.clearInterval(this.timer);
        this.closeClient();
    }

    private closeClient() {
        const client = this.client;
        this.client = null;
        this.pending?.finish('Disconnected before the controller confirmed the save.');
        // Paho cancels its reconnect timer in disconnect(), including while offline.
        try { client?.disconnect(); } catch { /* The socket may already be closed. */ }
    }

    handleLogin = (username: string, password: string) => {
        this.closeClient();
        this.setState({ session: 'connecting', loginError: '' });
        try {
            const uri = new URL('/terra/mqtt', window.location.href);
            uri.protocol = uri.protocol === 'https:' ? 'wss:' : 'ws:';
            const dev = process.env.NODE_ENV === 'development' && process.env.REACT_APP_DEV_MQTT_URL;
            const endpoint = dev ? new URL(dev) : uri;
            const client = new Paho.Client(endpoint.href, 'front_' + Math.random().toString(16).slice(2));
            this.client = client;
            client.onConnectionLost = () => {
                if (client !== this.client) return;
                this.pending?.finish('Connection lost before the save was confirmed.');
                this.setState({ session: 'offline', contact: 0, controls: {}, readings: {} });
            };
            client.onMessageArrived = message => {
                if (client === this.client) this.receive(message);
            };
            client.connect({
                userName: username, password, reconnect: true, keepAliveInterval: 30,
                useSSL: endpoint.protocol === 'wss:',
                onSuccess: () => {
                    if (client !== this.client) {
                        client.disconnect();
                        return;
                    }
                    this.setState({ session: 'online', config: null, contact: 0 });
                    for (const topic of ['sensor/+/temperature', 'sensor/+/humidity', 'mode', 'controls/state',
                        'config/status', 'config/full']) client.subscribe(topic);
                    this.publish('config/get', '1');
                },
                onFailure: () => {
                    if (client === this.client) this.loginFailed();
                }
            });
        } catch {
            this.loginFailed();
        }
    };

    private loginFailed() {
        this.closeClient();
        this.setState({ session: 'login', loginError: 'Could not sign in. Check the connection and credentials.' });
    }

    private publish(topic: string, payload: string) {
        if (!this.client?.isConnected()) return false;
        try {
            this.client.send(topic, payload, 0, false);
            return true;
        } catch {
            return false;
        }
    }

    private receive(message: Paho.Message) {
        const topic = message.destinationName;
        const text = message.payloadString;
        const now = Date.now();
        if (topic.startsWith('sensor/')) {
            if (text.trim() && Number.isFinite(Number(text))) {
                this.setState(state => ({ readings: { ...state.readings, [topic]: { value: text, at: now } } }));
            }
        } else if (topic === 'mode') {
            this.setState({ currentMode: text === 'None' ? '' : text });
        } else {
            try {
                const data = JSON.parse(text);
                if (topic === 'config/full' && data?.planning && data.modes && data.sensors) {
                    this.setState({ config: data, currentMode: data.current_mode || '', contact: now });
                } else if (topic === 'controls/state' && data && typeof data === 'object') {
                    this.setState({ controls: data, contact: now });
                } else if (topic === 'config/status' && this.pending && data.request_id === this.pending.id) {
                    this.pending.finish(data.success ? undefined : data.message || 'Settings were rejected.');
                }
            } catch { /* Ignore incomplete snapshots from older publishers. */ }
        }
    }

    saveSettings = (data: Pick<FullConfig, 'modes' | 'planning'>, revision: string): Promise<void> => {
        if (this.pending) return Promise.reject(new Error('A save is already pending.'));
        return new Promise((resolve, reject) => {
            const id = `${this.client?.clientId}-${++this.requestNumber}`;
            const finish = (error?: string) => {
                window.clearTimeout(timeout);
                this.pending = undefined;
                if (error) reject(new Error(error));
                else resolve();
            };
            const timeout = window.setTimeout(() => finish('Save unconfirmed. Check the latest settings.'), 10000);
            this.pending = { id, finish };
            if (!this.publish('config/update', JSON.stringify({ section: 'settings', data, revision, request_id: id }))) {
                finish('The dashboard is disconnected.');
            }
        });
    };

    onPlanningActiveChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const config = this.state.config;
        if (!config?.revision) return;
        try {
            await this.saveSettings({ modes: config.modes, planning: { ...config.planning, active: event.target.checked } }, config.revision);
        } catch (error) {
            this.showError(error instanceof Error ? error.message : 'Could not change planning.');
        }
    };

    onModeChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        if (!this.publish('mode/set', event.target.value)) this.showError('The dashboard is disconnected.');
    };

    private showError(message: string) {
        this.setState({ toast: { visible: true, type: 'error', message } });
    }

    onSettingsOpen = () => {
        if (this.publish('config/get', '1')) this.setState({ settingsVisible: true });
    };
    onSettingsClose = () => this.setState({ settingsVisible: false });
    onToastClose = () => this.setState(state => ({ toast: { ...state.toast, visible: false } }));
    onDisconnect = () => {
        this.closeClient();
        forgetLegacyCredentials();
        this.setState(initialState());
    };

    render() {
        const { config, session, controls, currentMode } = this.state;
        const live = session === 'online' && !!config && Date.now() - this.state.contact < 10000;
        const sensor = Object.keys(config?.sensors ?? {})[0];
        const reading = (field: string) => {
            const sample = this.state.readings[`sensor/${sensor}/${field}`];
            const maxAge = Math.max(10, 3 * (config?.log_interval ?? 5)) * 1000;
            return live && sample && Date.now() - sample.at < maxAge ? sample.value : '—';
        };
        return (
            <div id="terra" className="flex-container">

                {(session === 'offline' || (session === 'online' && !live)) &&
                    <div role="status">{session === 'offline' ? 'Broker disconnected. Reconnecting…' : 'Waiting for the controller'}
                        <button onClick={this.onDisconnect}>Disconnect</button>
                    </div>}
                <button className="settings-button" disabled={!live} onClick={this.onSettingsOpen} title="Settings">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M19.14 12.94c.04-.31.06-.63.06-.94 0-.31-.02-.63-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
                    </svg>
                </button>

                {/* Settings Modal */}
                <SettingsModal
                    visible={this.state.settingsVisible}
                    online={live}
                    config={config}
                    onClose={this.onSettingsClose}
                    onSave={this.saveSettings}
                    onDisconnect={this.onDisconnect}
                />

                {/* Toast Notification */}
                <Toast
                    visible={this.state.toast.visible}
                    message={this.state.toast.message}
                    type={this.state.toast.type}
                    onClose={this.onToastClose}
                />
                
                <div className="flex-column">
                    <div className="flex-row" id="sensors-row">
                        <div id="temperature">
                            <div className="centered">
                                <div>Temperature</div>
                                <div className="value">{reading("temperature")}°C</div>
                            </div>
                        </div>
                        
                        <div id="humidity">
                            <div className="centered">
                                <div>Humidity</div>
                                <div className="value">{reading("humidity")}%</div>
                            </div>
                        </div>
                    </div>


                    <div className="flex-row" id="controls-row" hidden={!live || !Object.keys(controls).length}>
                        <div id="control-light" style={{backgroundColor: controls.light ? "yellow" : "white"}}>
                            <Control state={controls.light}>
                                <img src={require("../resources/images/light.png")} alt="Light" style={{height: "60%"}}/>
                            </Control>
                        </div>
                        
                        <div id="control-cooling">
                            <Control state={controls.cooling_system}>
                                <img src={require("../resources/images/cooling-system.png")} className="fan-icon" alt="Cooling system" style={{height: "60%"}}/>
                            </Control>
                        </div>
                    </div>

                    <div className="flex-row" id="planning-row">
                        <div id="planning-checkbox">
                            <label className="checkbox-button">
                                <input type="checkbox" checked={!!config?.planning.active} disabled={!live || !config?.revision} onChange={this.onPlanningActiveChange}/>
                                <span className="checkmark"></span>
                                <span className="label-text">Planning</span>
                            </label>
                        </div>
                    </div>
                    
                    <div className="flex-row" id="mode-row">
                        <div id="mode">
                            <div className="dropdown">
                                <label htmlFor="mode-select">Mode</label>
                                <select id="mode-select" value={currentMode} onChange={this.onModeChange} disabled={!live || config?.planning.active}>
                                    <option value="">(None)</option>
                                    {Object.keys(config?.modes ?? {}).map((mode) => <option value={mode} key={mode}>{mode}</option>)}
                                </select>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Login Modal */}
                {(session === 'login' || session === 'connecting') && <LoginModal
                    connecting={session === 'connecting'}
                    onLogin={this.handleLogin}
                    error={this.state.loginError}
                />}
            </div>

        );
    }

}
