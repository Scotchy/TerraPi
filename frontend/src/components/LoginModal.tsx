import React from 'react';
import './login.css';

interface LoginModalProps {
    visible: boolean;
    onLogin: (username: string, password: string) => void;
    error?: string;
}

interface LoginModalState {
    username: string;
    password: string;
    showPassword: boolean;
    isLoading: boolean;
    biometricAvailable: boolean;
    biometricError: string;
}

export class LoginModal extends React.Component<LoginModalProps, LoginModalState> {
    constructor(props: LoginModalProps) {
        super(props);
        this.state = {
            username: '',
            password: '',
            showPassword: false,
            isLoading: false,
            biometricAvailable: false,
            biometricError: ''
        };
    }

    componentDidMount() {
        this.checkBiometricAvailability();
    }

    componentDidUpdate(prevProps: LoginModalProps) {
        // Reset loading state when an error is received or when modal becomes visible
        if (this.props.error && this.props.error !== prevProps.error) {
            this.setState({ isLoading: false });
        }
        // Also reset loading when modal is shown again
        if (this.props.visible && !prevProps.visible) {
            this.setState({ isLoading: false });
        }
    }

    checkBiometricAvailability = async () => {
        // Check if WebAuthn is available
        if (window.PublicKeyCredential) {
            try {
                const available = await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
                this.setState({ biometricAvailable: available });
            } catch (err) {
                console.log('Biometric check failed:', err);
                this.setState({ biometricAvailable: false });
            }
        }
    }

    handleUsernameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        this.setState({ username: e.target.value });
    }

    handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        this.setState({ password: e.target.value });
    }

    togglePasswordVisibility = () => {
        this.setState({ showPassword: !this.state.showPassword });
    }

    handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (this.state.username && this.state.password) {
            this.setState({ isLoading: true });
            this.props.onLogin(this.state.username, this.state.password);
        }
    }

    // Register biometric credential
    registerBiometric = async () => {
        const { username, password } = this.state;
        
        if (!username || !password) {
            this.setState({ biometricError: 'Please enter username and password first' });
            return;
        }

        try {
            this.setState({ isLoading: true, biometricError: '' });

            // Generate a random challenge
            const challenge = new Uint8Array(32);
            window.crypto.getRandomValues(challenge);

            // Create credential options
            const publicKeyCredentialCreationOptions: PublicKeyCredentialCreationOptions = {
                challenge: challenge,
                rp: {
                    name: "TerraPi",
                    id: window.location.hostname
                },
                user: {
                    id: new TextEncoder().encode(username),
                    name: username,
                    displayName: username
                },
                pubKeyCredParams: [
                    { alg: -7, type: "public-key" },  // ES256
                    { alg: -257, type: "public-key" } // RS256
                ],
                authenticatorSelection: {
                    authenticatorAttachment: "platform",
                    userVerification: "required",
                    residentKey: "required"
                },
                timeout: 60000,
                attestation: "none"
            };

            const credential = await navigator.credentials.create({
                publicKey: publicKeyCredentialCreationOptions
            }) as PublicKeyCredential;

            if (credential) {
                // Store the credential ID and user credentials
                const rawIdArray = new Uint8Array(credential.rawId);
                const credentialId = btoa(String.fromCharCode.apply(null, Array.from(rawIdArray)));
                localStorage.setItem('terrapi_credential_id', credentialId);
                localStorage.setItem('terrapi_biometric_user', username);
                // Store encrypted password (in production, use proper encryption)
                localStorage.setItem('terrapi_biometric_pass', btoa(password));
                
                this.setState({ biometricError: '' });
                alert('Fingerprint registered successfully! You can now use biometric login.');
            }
        } catch (err: any) {
            console.error('Biometric registration failed:', err);
            this.setState({ biometricError: err.message || 'Registration failed' });
        } finally {
            this.setState({ isLoading: false });
        }
    }

    // Authenticate with biometric
    authenticateWithBiometric = async () => {
        try {
            this.setState({ isLoading: true, biometricError: '' });

            const storedCredentialId = localStorage.getItem('terrapi_credential_id');
            
            if (!storedCredentialId) {
                this.setState({ biometricError: 'No biometric registered. Please login with password first and register your fingerprint.' });
                this.setState({ isLoading: false });
                return;
            }

            // Generate a random challenge
            const challenge = new Uint8Array(32);
            window.crypto.getRandomValues(challenge);

            // Decode the stored credential ID
            const credentialIdBytes = Uint8Array.from(atob(storedCredentialId), c => c.charCodeAt(0));

            const publicKeyCredentialRequestOptions: PublicKeyCredentialRequestOptions = {
                challenge: challenge,
                allowCredentials: [{
                    id: credentialIdBytes,
                    type: 'public-key',
                    transports: ['internal']
                }],
                userVerification: "required",
                timeout: 60000
            };

            const assertion = await navigator.credentials.get({
                publicKey: publicKeyCredentialRequestOptions
            });

            if (assertion) {
                // Retrieve stored credentials
                const username = localStorage.getItem('terrapi_biometric_user');
                const password = localStorage.getItem('terrapi_biometric_pass');
                
                if (username && password) {
                    this.props.onLogin(username, atob(password));
                } else {
                    this.setState({ biometricError: 'Stored credentials not found. Please login with password.' });
                }
            }
        } catch (err: any) {
            console.error('Biometric authentication failed:', err);
            if (err.name === 'NotAllowedError') {
                this.setState({ biometricError: 'Authentication cancelled or not allowed' });
            } else {
                this.setState({ biometricError: err.message || 'Authentication failed' });
            }
        } finally {
            this.setState({ isLoading: false });
        }
    }

    render() {
        if (!this.props.visible) {
            return null;
        }

        const hasStoredBiometric = localStorage.getItem('terrapi_credential_id') !== null;

        return (
            <div className="login-overlay">
                <div className="login-modal">
                    <div className="login-header">
                        <div className="login-logo">
                            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                            </svg>
                        </div>
                        <h1>TerraPi</h1>
                        <p>Terrarium Control System</p>
                    </div>

                    <form className="login-form" onSubmit={this.handleSubmit}>
                        {this.props.error && (
                            <div className="login-error">
                                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                                </svg>
                                <span>{this.props.error}</span>
                            </div>
                        )}

                        <div className="input-group">
                            <div className="input-icon">
                                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                                </svg>
                            </div>
                            <input
                                type="text"
                                placeholder="Username"
                                value={this.state.username}
                                onChange={this.handleUsernameChange}
                                autoComplete="username"
                                autoFocus
                            />
                        </div>

                        <div className="input-group">
                            <div className="input-icon">
                                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
                                </svg>
                            </div>
                            <input
                                type={this.state.showPassword ? "text" : "password"}
                                placeholder="Password"
                                value={this.state.password}
                                onChange={this.handlePasswordChange}
                                autoComplete="current-password"
                            />
                            <button
                                type="button"
                                className="password-toggle"
                                onClick={this.togglePasswordVisibility}
                            >
                                {this.state.showPassword ? (
                                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
                                    </svg>
                                ) : (
                                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
                                    </svg>
                                )}
                            </button>
                        </div>

                        <button
                            type="submit"
                            className="login-button"
                            disabled={this.state.isLoading || !this.state.username || !this.state.password}
                        >
                            {this.state.isLoading ? (
                                <span className="loading-spinner"></span>
                            ) : (
                                'Sign In'
                            )}
                        </button>

                        {this.state.biometricAvailable && (
                            <>
                                <div className="login-divider">
                                    <span>or</span>
                                </div>

                                <button
                                    type="button"
                                    className="biometric-button"
                                    onClick={this.authenticateWithBiometric}
                                    disabled={this.state.isLoading || !hasStoredBiometric}
                                    title={hasStoredBiometric ? "Login with fingerprint" : "Register your fingerprint first"}
                                >
                                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M17.81 4.47c-.08 0-.16-.02-.23-.06C15.66 3.42 14 3 12.01 3c-1.98 0-3.86.47-5.57 1.41-.24.13-.54.04-.68-.2-.13-.24-.04-.55.2-.68C7.82 2.52 9.86 2 12.01 2c2.13 0 3.99.47 6.03 1.52.25.13.34.43.21.67-.09.18-.26.28-.44.28zM3.5 9.72c-.1 0-.2-.03-.29-.09-.23-.16-.28-.47-.12-.7.99-1.4 2.25-2.5 3.75-3.27C9.98 4.04 14 4.03 17.15 5.65c1.5.77 2.76 1.86 3.75 3.25.16.22.11.54-.12.7-.23.16-.54.11-.7-.12-.9-1.26-2.04-2.25-3.39-2.94-2.87-1.47-6.54-1.47-9.4.01-1.36.7-2.5 1.7-3.4 2.96-.08.14-.23.21-.39.21zm6.25 12.07c-.13 0-.26-.05-.35-.15-.87-.87-1.34-1.43-2.01-2.64-.69-1.23-1.05-2.73-1.05-4.34 0-2.97 2.54-5.39 5.66-5.39s5.66 2.42 5.66 5.39c0 .28-.22.5-.5.5s-.5-.22-.5-.5c0-2.42-2.09-4.39-4.66-4.39-2.57 0-4.66 1.97-4.66 4.39 0 1.44.32 2.77.93 3.85.64 1.15 1.08 1.64 1.85 2.42.19.2.19.51 0 .71-.11.1-.24.15-.37.15zm7.17-1.85c-1.19 0-2.24-.3-3.1-.89-1.49-1.01-2.38-2.65-2.38-4.39 0-.28.22-.5.5-.5s.5.22.5.5c0 1.41.72 2.74 1.94 3.56.71.48 1.54.71 2.54.71.24 0 .64-.03 1.04-.1.27-.05.53.13.58.41.05.27-.13.53-.41.58-.57.11-1.07.12-1.21.12zM14.91 22c-.04 0-.09-.01-.13-.02-1.59-.44-2.63-1.03-3.72-2.1-1.4-1.39-2.17-3.24-2.17-5.22 0-1.62 1.38-2.94 3.08-2.94 1.7 0 3.08 1.32 3.08 2.94 0 1.07.93 1.94 2.08 1.94s2.08-.87 2.08-1.94c0-3.77-3.25-6.83-7.25-6.83-2.84 0-5.44 1.58-6.61 4.03-.39.81-.59 1.76-.59 2.8 0 .78.07 2.01.67 3.61.1.26-.03.55-.29.64-.26.1-.55-.04-.64-.29-.49-1.31-.73-2.61-.73-3.96 0-1.2.23-2.29.68-3.24 1.33-2.79 4.28-4.6 7.51-4.6 4.55 0 8.25 3.51 8.25 7.83 0 1.62-1.38 2.94-3.08 2.94s-3.08-1.32-3.08-2.94c0-1.07-.93-1.94-2.08-1.94s-2.08.87-2.08 1.94c0 1.71.66 3.31 1.87 4.51.95.94 1.86 1.46 3.27 1.85.27.07.42.35.35.61-.05.23-.26.38-.47.38z"/>
                                    </svg>
                                    <span>Login with Fingerprint</span>
                                </button>

                                {this.state.username && this.state.password && !hasStoredBiometric && (
                                    <button
                                        type="button"
                                        className="register-biometric-button"
                                        onClick={this.registerBiometric}
                                        disabled={this.state.isLoading}
                                    >
                                        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                            <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
                                        </svg>
                                        <span>Register Fingerprint</span>
                                    </button>
                                )}

                                {hasStoredBiometric && (
                                    <button
                                        type="button"
                                        className="clear-biometric-button"
                                        onClick={() => {
                                            localStorage.removeItem('terrapi_credential_id');
                                            localStorage.removeItem('terrapi_biometric_user');
                                            localStorage.removeItem('terrapi_biometric_pass');
                                            this.forceUpdate();
                                        }}
                                    >
                                        Remove saved fingerprint
                                    </button>
                                )}

                                {this.state.biometricError && (
                                    <div className="biometric-error">
                                        {this.state.biometricError}
                                    </div>
                                )}
                            </>
                        )}
                    </form>

                    <div className="login-footer">
                        <p>🌿 Monitor and control your terrarium</p>
                    </div>
                </div>
            </div>
        );
    }
}
