import React, { useState } from 'react';
import './login.css';

interface Props {
    connecting: boolean;
    error: string;
    onLogin: (username: string, password: string) => void;
}

export function LoginModal({ connecting, error, onLogin }: Props) {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);

    function submit(event: React.FormEvent) {
        event.preventDefault();
        if (username && password && !connecting) onLogin(username, password);
    }

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

                <form className="login-form" onSubmit={submit}>
                    {error && (
                        <div className="login-error">
                            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                            </svg>
                            <span>{error}</span>
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
                            value={username}
                            onChange={e => setUsername(e.target.value)}
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
                            type={showPassword ? "text" : "password"}
                            placeholder="Password"
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            autoComplete="current-password"
                        />
                        <button
                            type="button"
                            className="password-toggle"
                            onClick={() => setShowPassword(!showPassword)}
                        >
                            {showPassword ? (
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
                        disabled={connecting || !username || !password}
                    >
                        {connecting ? (
                            <span className="loading-spinner"></span>
                        ) : (
                            'Sign In'
                        )}
                    </button>

                </form>
            </div>
        </div>
    );
}
