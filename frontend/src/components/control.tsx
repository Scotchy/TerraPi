import * as React from 'react';
import "./control.css"

interface ControlProps {
    state: boolean
}

interface ControlState {

}

export class Control extends React.Component<ControlProps, ControlState> {

    constructor(props : ControlProps) {
        super(props);
    }

    render() {
        return (
            <div className={"control control-" + (this.props.state ? "on" : "off")}>
                {this.props.children}
            </div>
        );
    }

}
