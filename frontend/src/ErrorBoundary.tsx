import { Component, type ErrorInfo, type ReactNode } from "react";

type State = { error: Error | null };

/** A crash in one screen must never blank the whole app. It is shown as text, with a way back. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Screen crashed", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main>
        <h1>Bid Workbench</h1>
        <p className="alert" role="alert">This screen hit an error: {this.state.error.message}</p>
        <p className="note">
          <a href="#/setup" onClick={() => this.setState({ error: null })}>Back to Setup</a>. If it happens again, run <code>docker compose logs api</code> and send us the last lines.
        </p>
      </main>
    );
  }
}
