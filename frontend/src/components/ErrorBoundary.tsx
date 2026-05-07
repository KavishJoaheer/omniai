import { Component, ErrorInfo, ReactNode } from "react";

type Props = {
  children: ReactNode;
};

type State = {
  error: Error | null;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page render failed", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <section className="page">
        <div className="panel stack" role="alert">
          <div>
            <p className="eyebrow">Recovery</p>
            <h2>Something on this page crashed</h2>
          </div>
          <p className="alert">{this.state.error.message || "Unexpected page error."}</p>
          <div className="button-row">
            <button
              className="primary-button"
              type="button"
              onClick={() => this.setState({ error: null })}
            >
              Try again
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => window.location.assign("/")}
            >
              Back to overview
            </button>
          </div>
        </div>
      </section>
    );
  }
}
