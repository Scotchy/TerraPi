import * as mqtt from 'react-paho-mqtt';

import React from 'react';
import { Control } from './control';
import { SettingsModal } from './SettingsModal';
import { Toast } from './Toast';
import './settings.css';

interface TerraProps {
   
}

interface FullConfig {
    modes: { [modeName: string]: { [controlName: string]: boolean } };
    planning: {
        active: boolean;
        default_mode: string;
        periods: { [periodName: string]: { start: string; end: string; mode: string } };
    };
    sensors: { [sensorName: string]: { type: string } };
    controls: { [controlName: string]: { type: string } };
    log_interval: number;
    current_mode?: string;
}

interface TerraState {
    temperature: string,
    humidity: string,
    planning_active: boolean | undefined,
    modes: string[],
    current_mode: string,
    controls_state: { [control: string]: boolean },
    settingsVisible: boolean,
    fullConfig: FullConfig | null,
    toast: {
        visible: boolean,
        message: string,
        type: 'success' | 'error'
    }
}

export class Terra extends React.Component<TerraProps, TerraState> {
    
    client: any;

    constructor(props : TerraProps) {
        super(props);
        this.state = {
            temperature: "-",
            humidity: "-",
            planning_active: undefined,
            modes: [],
            current_mode: "",
            controls_state: {},
            settingsVisible: false,
            fullConfig: null,
            toast: {
                visible: false,
                message: '',
                type: 'success'
            }
        };
        this.client = null;
    }

    connect(askCredentials : boolean = false) {

        if (this.client !== null && this.client.isConnected()) {
            this.client.disconnect();
        }

        const cookies = document.cookie.split(';');
        let username : string | null = null;
        let password : string | null = null;

        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.startsWith("username=")) {
            username = cookie.substring("username=".length, cookie.length);
            } else if (cookie.startsWith("password=")) {
            password = cookie.substring("password=".length, cookie.length);
            }
        }

        // Prompt for username and password if not found in cookies
        if (askCredentials || username === null || password === null) {
            username = prompt("Username");
            password = prompt("Password");
            document.cookie = "username=" + username;
            document.cookie = "password=" + password;
        }

        // Generate unique client ID to avoid conflicts
        const clientId = "front_" + Math.random().toString(16).substring(2, 10);
        
        this.client = mqtt.connect(
            "plantescarnivores.net", 
            9001, 
            clientId, 
            this.onConnectionLost, 
            this.onMessageArrived
        );

        const options = {
            userName: username,
            password: password,
            onSuccess: this.onConnect,
            onFailure: this.onConnectionLost,
            reconnect: true,
            keepAliveInterval: 30
        };

        this.client.connect(options);

        this.client.onConnectionLost = this.onConnectionLost;
        this.client.onMessageArrived = this.onMessageArrived;
    }

    componentDidMount() {
        this.connect();
    }

    onConnect = () => {
        console.log("Connected to MQTT server");

        // Subscribe to sensor/dht22/temperature and sensor/dht22/humidity
        this.client.subscribe("sensor/dht22/temperature");
        this.client.subscribe("sensor/dht22/humidity");
        this.client.subscribe("controls/state");
        this.client.subscribe("conf");
        this.client.subscribe("config/full");
        this.client.subscribe("config/status");

        // Get current conf
        console.log("Publishing config/get request...");
        this.client.publish("config/get", "1");
    }

    componentWillUnmount() {
        this.client.disconnect();
    }

    onConnectionLost = (responseObject : any) => {
        if (responseObject.errorCode !== 0) {
            console.log("onConnectionLost:" + responseObject.errorMessage);
        }
    }

    onMessageArrived = (message : any) => {
        console.log("onMessageArrived: topic=" + message.destinationName + " payload=" + message.payloadString?.substring(0, 100));
        if (message.destinationName === "sensor/dht22/temperature") {
            this.setState({
                temperature: message.payloadString
            });
        } else if (message.destinationName === "sensor/dht22/humidity") {
            this.setState({
                humidity: message.payloadString
            });
        } else if (message.destinationName === "conf") {
            const conf = JSON.parse(message.payloadString);
            this.setState({
                planning_active: conf.planning.active,
                modes: conf.modes,
                current_mode: conf.current_mode
            });
        } else if (message.destinationName === "config/full") {
            // Full configuration received
            const fullConfig = JSON.parse(message.payloadString);
            this.setState({
                fullConfig: fullConfig,
                planning_active: fullConfig.planning.active,
                modes: Object.keys(fullConfig.modes),
                current_mode: fullConfig.current_mode || fullConfig.planning.default_mode
            });
        } else if (message.destinationName === "config/status") {
            // Configuration update status
            const status = JSON.parse(message.payloadString);
            this.setState({
                toast: {
                    visible: true,
                    message: status.message,
                    type: status.success ? 'success' : 'error'
                }
            });
        } else if (message.destinationName === "controls/state") {
            const state = JSON.parse(message.payloadString);
            this.setState({
                controls_state: state
            });
            
        }


    }
    
    onPlanningActiveChange = (event : any) => {
        this.setState({
            planning_active: event.target.checked
        });
        this.client.publish("planning/active", event.target.checked ? "1" : "0");
        this.client.publish("config/get", "1");
    }

    onModeChange = (event : any) => {
        this.setState({
            current_mode: event.target.value
        });
        this.client.publish("mode/set", event.target.value);
    }

    onSettingsOpen = () => {
        // Request fresh config before opening settings
        console.log("Settings opened, publishing config/get...");
        this.client.publish("config/get", "1");
        this.setState({ settingsVisible: true });
    }

    onSettingsClose = () => {
        this.setState({ settingsVisible: false });
    }

    onSettingsSave = (section: string, data: any) => {
        const update = JSON.stringify({ section, data });
        this.client.publish("config/update", update);
    }

    onToastClose = () => {
        this.setState({
            toast: { ...this.state.toast, visible: false }
        });
    }

    render() {
        return (
            <div id="terra" className="flex-container">

                {/* Settings Button */}
                <button className="settings-button" onClick={this.onSettingsOpen} title="Settings">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M19.14 12.94c.04-.31.06-.63.06-.94 0-.31-.02-.63-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
                    </svg>
                </button>

                {/* Settings Modal */}
                <SettingsModal
                    visible={this.state.settingsVisible}
                    config={this.state.fullConfig}
                    onClose={this.onSettingsClose}
                    onSave={this.onSettingsSave}
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
                                <div className="value">{this.state.temperature}°C</div>
                            </div>
                        </div>
                        
                        <div id="humidity">
                            <div className="centered">
                                <div>Humidity</div>
                                <div className="value">{this.state.humidity}%</div>
                            </div>
                        </div>
                    </div>


                    <div className="flex-row" id="controls-row">
                        <div id="control-light" style={{backgroundColor: this.state.controls_state.light ? "yellow" : "white"}}>
                            <Control state={this.state.controls_state.light}>
                                <img src={require("../resources/images/light.png")} alt="Light" style={{height: "60%"}}/>
                            </Control>
                        </div>
                        
                        <div id="control-cooling">
                            <Control state={this.state.controls_state.cooling_system}>
                                <img src={require("../resources/images/cooling-system.png")} className="fan-icon" alt="Cooling system" style={{height: "60%"}}/>
                            </Control>
                        </div>
                    </div>

                    <div className="flex-row" id="planning-row">
                        <div id="planning-checkbox">
                            <label className="checkbox-button">
                                <input type="checkbox" id="planning-checkbox" defaultChecked={this.state.planning_active} onClick={this.onPlanningActiveChange}/>
                                <span className="checkmark"></span>
                                <span className="label-text">Planning</span>
                            </label>
                        </div>
                    </div>
                    
                    <div className="flex-row" id="mode-row">
                        <div id="mode">
                            <div className="dropdown">
                                <label>Mode</label>
                                <select value={this.state.current_mode} onChange={this.onModeChange} disabled={this.state.planning_active || this.state.planning_active === undefined || this.state.modes.length === 0}>
                                    {this.state.modes.map((mode) => <option value={mode} key={mode}>{mode}</option>)}
                                </select>
                            </div>
                        </div>
                    </div>

                    <div className="flex-row" id="change-login-row">
                        <div className="change-login">
                            <input type="button" value="Change login" onClick={() => {
                                this.connect(true);
                            }
                            }/>
                        </div>
                    </div>
                </div>
            </div>

        );
    }

}