import * as React from 'react';

interface Mode {
    [controlName: string]: boolean;
}

interface Period {
    start: string;
    end: string;
    mode: string;
}

interface FullConfig {
    modes: { [modeName: string]: Mode };
    planning: {
        active: boolean;
        default_mode: string;
        periods: { [periodName: string]: Period };
    };
    sensors: { [sensorName: string]: { type: string } };
    controls: { [controlName: string]: { type: string } };
    log_interval: number;
    current_mode?: string;
}

interface SettingsModalProps {
    visible: boolean;
    config: FullConfig | null;
    onClose: () => void;
    onSave: (section: string, data: any) => void;
}

interface SettingsModalState {
    activeTab: 'modes' | 'planning';
    editedModes: { [modeName: string]: Mode };
    editedPlanning: {
        active: boolean;
        default_mode: string;
        periods: { [periodName: string]: Period };
    };
    hasChanges: boolean;
}

export class SettingsModal extends React.Component<SettingsModalProps, SettingsModalState> {
    constructor(props: SettingsModalProps) {
        super(props);
        this.state = {
            activeTab: 'modes',
            editedModes: {},
            editedPlanning: { active: false, default_mode: '', periods: {} },
            hasChanges: false
        };
    }

    componentDidUpdate(prevProps: SettingsModalProps) {
        // Reset state when modal opens with new config
        if (this.props.visible && !prevProps.visible && this.props.config) {
            this.setState({
                editedModes: JSON.parse(JSON.stringify(this.props.config.modes)),
                editedPlanning: JSON.parse(JSON.stringify(this.props.config.planning)),
                hasChanges: false
            });
        }
    }

    handleModeControlChange = (modeName: string, controlName: string, value: boolean) => {
        this.setState(prevState => ({
            editedModes: {
                ...prevState.editedModes,
                [modeName]: {
                    ...prevState.editedModes[modeName],
                    [controlName]: value
                }
            },
            hasChanges: true
        }));
    };

    handlePlanningActiveChange = (active: boolean) => {
        this.setState(prevState => ({
            editedPlanning: {
                ...prevState.editedPlanning,
                active
            },
            hasChanges: true
        }));
    };

    handleDefaultModeChange = (defaultMode: string) => {
        this.setState(prevState => ({
            editedPlanning: {
                ...prevState.editedPlanning,
                default_mode: defaultMode
            },
            hasChanges: true
        }));
    };

    handlePeriodChange = (periodName: string, field: 'start' | 'end' | 'mode', value: string) => {
        this.setState(prevState => ({
            editedPlanning: {
                ...prevState.editedPlanning,
                periods: {
                    ...prevState.editedPlanning.periods,
                    [periodName]: {
                        ...prevState.editedPlanning.periods[periodName],
                        [field]: value
                    }
                }
            },
            hasChanges: true
        }));
    };

    handleSave = () => {
        if (this.state.activeTab === 'modes') {
            this.props.onSave('modes', this.state.editedModes);
        } else {
            this.props.onSave('planning', this.state.editedPlanning);
        }
        this.setState({ hasChanges: false });
    };

    handleClose = () => {
        this.setState({ hasChanges: false });
        this.props.onClose();
    };

    getControlNames(): string[] {
        if (!this.props.config) return [];
        return Object.keys(this.props.config.controls);
    }

    getModeNames(): string[] {
        return Object.keys(this.state.editedModes);
    }

    renderModesTab() {
        const controlNames = this.getControlNames();
        const modeNames = this.getModeNames();

        return (
            <div className="settings-section">
                <h3>Modes Configuration</h3>
                <p className="settings-hint">Configure which controls are active in each mode.</p>
                
                <table className="settings-table">
                    <thead>
                        <tr>
                            <th>Mode</th>
                            {controlNames.map(control => (
                                <th key={control}>{control}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {modeNames.map(modeName => (
                            <tr key={modeName}>
                                <td className="mode-name">{modeName}</td>
                                {controlNames.map(controlName => (
                                    <td key={controlName}>
                                        <label className="toggle-switch">
                                            <input
                                                type="checkbox"
                                                checked={this.state.editedModes[modeName]?.[controlName] || false}
                                                onChange={(e) => this.handleModeControlChange(modeName, controlName, e.target.checked)}
                                            />
                                            <span className="toggle-slider"></span>
                                        </label>
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    }

    renderPlanningTab() {
        const modeNames = this.getModeNames();
        const periods = this.state.editedPlanning.periods;

        return (
            <div className="settings-section">
                <h3>Planning Configuration</h3>
                
                <div className="settings-field">
                    <label>
                        <span>Planning Active</span>
                        <label className="toggle-switch">
                            <input
                                type="checkbox"
                                checked={this.state.editedPlanning.active}
                                onChange={(e) => this.handlePlanningActiveChange(e.target.checked)}
                            />
                            <span className="toggle-slider"></span>
                        </label>
                    </label>
                </div>

                <div className="settings-field">
                    <label>
                        <span>Default Mode</span>
                        <select
                            value={this.state.editedPlanning.default_mode}
                            onChange={(e) => this.handleDefaultModeChange(e.target.value)}
                        >
                            {modeNames.map(mode => (
                                <option key={mode} value={mode}>{mode}</option>
                            ))}
                        </select>
                    </label>
                </div>

                <h4>Periods</h4>
                <table className="settings-table">
                    <thead>
                        <tr>
                            <th>Period</th>
                            <th>Start</th>
                            <th>End</th>
                            <th>Mode</th>
                        </tr>
                    </thead>
                    <tbody>
                        {Object.keys(periods).map(periodName => (
                            <tr key={periodName}>
                                <td className="mode-name">{periodName}</td>
                                <td>
                                    <input
                                        type="time"
                                        value={periods[periodName].start}
                                        onChange={(e) => this.handlePeriodChange(periodName, 'start', e.target.value)}
                                    />
                                </td>
                                <td>
                                    <input
                                        type="time"
                                        value={periods[periodName].end}
                                        onChange={(e) => this.handlePeriodChange(periodName, 'end', e.target.value)}
                                    />
                                </td>
                                <td>
                                    <select
                                        value={periods[periodName].mode}
                                        onChange={(e) => this.handlePeriodChange(periodName, 'mode', e.target.value)}
                                    >
                                        {modeNames.map(mode => (
                                            <option key={mode} value={mode}>{mode}</option>
                                        ))}
                                    </select>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    }

    render() {
        if (!this.props.visible) {
            return null;
        }

        return (
            <div className="modal-overlay" onClick={this.handleClose}>
                <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                    <div className="modal-header">
                        <h2>Settings</h2>
                        <button className="modal-close" onClick={this.handleClose}>×</button>
                    </div>

                    <div className="modal-tabs">
                        <button
                            className={`tab-button ${this.state.activeTab === 'modes' ? 'active' : ''}`}
                            onClick={() => this.setState({ activeTab: 'modes' })}
                        >
                            Modes
                        </button>
                        <button
                            className={`tab-button ${this.state.activeTab === 'planning' ? 'active' : ''}`}
                            onClick={() => this.setState({ activeTab: 'planning' })}
                        >
                            Planning
                        </button>
                    </div>

                    <div className="modal-body">
                        {this.state.activeTab === 'modes' && this.renderModesTab()}
                        {this.state.activeTab === 'planning' && this.renderPlanningTab()}
                    </div>

                    <div className="modal-footer">
                        <button className="btn btn-secondary" onClick={this.handleClose}>
                            Cancel
                        </button>
                        <button 
                            className="btn btn-primary" 
                            onClick={this.handleSave}
                            disabled={!this.state.hasChanges}
                        >
                            Save Changes
                        </button>
                    </div>
                </div>
            </div>
        );
    }
}
