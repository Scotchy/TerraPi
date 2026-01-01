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

    handleModeNameChange = (oldName: string, newName: string) => {
        if (newName === oldName) return;
        if (newName.trim() === '') return;
        
        this.setState(prevState => {
            const { [oldName]: modeData, ...restModes } = prevState.editedModes;
            
            // Also update any references in planning periods
            const updatedPeriods = { ...prevState.editedPlanning.periods };
            Object.keys(updatedPeriods).forEach(periodName => {
                if (updatedPeriods[periodName].mode === oldName) {
                    updatedPeriods[periodName] = {
                        ...updatedPeriods[periodName],
                        mode: newName
                    };
                }
            });
            
            // Update default_mode if it references the renamed mode
            const updatedDefaultMode = prevState.editedPlanning.default_mode === oldName 
                ? newName 
                : prevState.editedPlanning.default_mode;
            
            return {
                editedModes: {
                    ...restModes,
                    [newName]: modeData
                },
                editedPlanning: {
                    ...prevState.editedPlanning,
                    default_mode: updatedDefaultMode,
                    periods: updatedPeriods
                },
                hasChanges: true
            };
        });
    };

    handleAddMode = () => {
        const controlNames = this.getControlNames();
        
        // Generate a unique mode name
        let newModeName = 'new_mode';
        let counter = 1;
        while (this.state.editedModes[newModeName]) {
            newModeName = `new_mode_${counter}`;
            counter++;
        }
        
        // Create mode with all controls set to false
        const newModeData: { [controlName: string]: boolean } = {};
        controlNames.forEach(control => {
            newModeData[control] = false;
        });
        
        this.setState(prevState => ({
            editedModes: {
                ...prevState.editedModes,
                [newModeName]: newModeData
            },
            hasChanges: true
        }));
    };

    handleDeleteMode = (modeName: string) => {
        // Prevent deleting the last mode
        if (Object.keys(this.state.editedModes).length <= 1) {
            return;
        }
        
        this.setState(prevState => {
            const { [modeName]: _, ...restModes } = prevState.editedModes;
            const remainingModes = Object.keys(restModes);
            
            // Set periods using the deleted mode to empty (None) - they will do nothing
            const updatedPeriods = { ...prevState.editedPlanning.periods };
            Object.keys(updatedPeriods).forEach(periodName => {
                if (updatedPeriods[periodName].mode === modeName) {
                    updatedPeriods[periodName] = {
                        ...updatedPeriods[periodName],
                        mode: ''
                    };
                }
            });
            
            // Default mode still needs a valid mode, use first remaining
            const updatedDefaultMode = prevState.editedPlanning.default_mode === modeName
                ? remainingModes[0] || ''
                : prevState.editedPlanning.default_mode;
            
            return {
                editedModes: restModes,
                editedPlanning: {
                    ...prevState.editedPlanning,
                    default_mode: updatedDefaultMode,
                    periods: updatedPeriods
                },
                hasChanges: true
            };
        });
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

    handlePeriodNameChange = (oldName: string, newName: string) => {
        if (newName === oldName) return;
        if (newName.trim() === '') return;
        
        this.setState(prevState => {
            const { [oldName]: periodData, ...restPeriods } = prevState.editedPlanning.periods;
            return {
                editedPlanning: {
                    ...prevState.editedPlanning,
                    periods: {
                        ...restPeriods,
                        [newName]: periodData
                    }
                },
                hasChanges: true
            };
        });
    };

    handleAddPeriod = () => {
        const modeNames = this.getModeNames();
        const defaultMode = modeNames.length > 0 ? modeNames[0] : '';
        
        // Generate a unique period name
        let newPeriodName = 'new_period';
        let counter = 1;
        while (this.state.editedPlanning.periods[newPeriodName]) {
            newPeriodName = `new_period_${counter}`;
            counter++;
        }
        
        this.setState(prevState => ({
            editedPlanning: {
                ...prevState.editedPlanning,
                periods: {
                    ...prevState.editedPlanning.periods,
                    [newPeriodName]: {
                        start: '00:00',
                        end: '00:00',
                        mode: defaultMode
                    }
                }
            },
            hasChanges: true
        }));
    };

    handleDeletePeriod = (periodName: string) => {
        this.setState(prevState => {
            const { [periodName]: _, ...restPeriods } = prevState.editedPlanning.periods;
            return {
                editedPlanning: {
                    ...prevState.editedPlanning,
                    periods: restPeriods
                },
                hasChanges: true
            };
        });
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
        const canDelete = modeNames.length > 1;

        return (
            <div className="settings-section">
                <div className="section-header">
                    <div>
                        <h3>Modes Configuration</h3>
                        <p className="settings-hint">Configure which controls are active in each mode.</p>
                    </div>
                    <button 
                        className="btn btn-add" 
                        onClick={this.handleAddMode}
                        title="Add new mode"
                    >
                        + Add Mode
                    </button>
                </div>
                
                <table className="settings-table">
                    <thead>
                        <tr>
                            <th>Mode Name</th>
                            {controlNames.map(control => (
                                <th key={control}>{control}</th>
                            ))}
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {modeNames.map(modeName => (
                            <tr key={modeName}>
                                <td>
                                    <input
                                        type="text"
                                        className="mode-name-input"
                                        defaultValue={modeName}
                                        onBlur={(e) => this.handleModeNameChange(modeName, e.target.value.trim())}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter') {
                                                (e.target as HTMLInputElement).blur();
                                            }
                                        }}
                                    />
                                </td>
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
                                <td>
                                    <button
                                        className="btn-delete"
                                        onClick={() => this.handleDeleteMode(modeName)}
                                        title={canDelete ? "Delete mode" : "Cannot delete the last mode"}
                                        disabled={!canDelete}
                                    >
                                        ×
                                    </button>
                                </td>
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

                <div className="section-header">
                    <h4>Periods</h4>
                    <button 
                        className="btn btn-add" 
                        onClick={this.handleAddPeriod}
                        title="Add new period"
                    >
                        + Add Period
                    </button>
                </div>
                <table className="settings-table">
                    <thead>
                        <tr>
                            <th>Period Name</th>
                            <th>Start</th>
                            <th>End</th>
                            <th>Mode</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {Object.keys(periods).map(periodName => (
                            <tr key={periodName}>
                                <td>
                                    <input
                                        type="text"
                                        className="period-name-input"
                                        defaultValue={periodName}
                                        onBlur={(e) => this.handlePeriodNameChange(periodName, e.target.value.trim())}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter') {
                                                (e.target as HTMLInputElement).blur();
                                            }
                                        }}
                                    />
                                </td>
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
                                        className={periods[periodName].mode === '' ? 'mode-none' : ''}
                                    >
                                        <option value="" className="mode-none-option">(None)</option>
                                        {modeNames.map(mode => (
                                            <option key={mode} value={mode}>{mode}</option>
                                        ))}
                                    </select>
                                </td>
                                <td>
                                    <button
                                        className="btn-delete"
                                        onClick={() => this.handleDeletePeriod(periodName)}
                                        title="Delete period"
                                    >
                                        ×
                                    </button>
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
