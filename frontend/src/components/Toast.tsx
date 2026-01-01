import * as React from 'react';

interface ToastProps {
    message: string;
    type: 'success' | 'error';
    visible: boolean;
    onClose: () => void;
}

interface ToastState {}

export class Toast extends React.Component<ToastProps, ToastState> {
    private timeoutId: NodeJS.Timeout | null = null;

    componentDidUpdate(prevProps: ToastProps) {
        if (this.props.visible && !prevProps.visible) {
            // Clear existing timeout
            if (this.timeoutId) {
                clearTimeout(this.timeoutId);
            }
            // Auto-hide after 4 seconds
            this.timeoutId = setTimeout(() => {
                this.props.onClose();
            }, 4000);
        }
    }

    componentWillUnmount() {
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
        }
    }

    render() {
        if (!this.props.visible) {
            return null;
        }

        return (
            <div className={`toast toast-${this.props.type}`} onClick={this.props.onClose}>
                <span className="toast-message">{this.props.message}</span>
                <span className="toast-close">×</span>
            </div>
        );
    }
}
