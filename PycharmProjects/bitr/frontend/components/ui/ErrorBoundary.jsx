"use client";

import { Component } from "react";

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      
      return (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-center">
          <div className="text-4xl mb-4">⚠️</div>
          <h3 className="text-xl font-semibold text-white mb-2">Ошибка компонента</h3>
          <p className="text-dashboard-text-muted mb-4">
            {this.state.error?.message || "Произошла ошибка при отображении"}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.reload();
            }}
            className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors"
          >
            Перезагрузить
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;

