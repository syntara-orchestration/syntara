import { Component, type ReactNode } from 'react'

import { SynPage, SynPageBody } from './layout/SynPage'
import { SynPageHeader } from './layout/SynPageHeader'
import { SynPanel } from './layout/SynPanel'
import { SynErrorState } from './states/SynErrorState'

type ErrorBoundaryProps = {
  children: ReactNode
  fallback?: ReactNode
}

type ErrorBoundaryState = {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch() {
    // Error boundary caught an error
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <SynPage>
          <SynPageHeader title="Something went wrong" />
          <SynPageBody>
            <SynPanel isFullHeight>
              <SynErrorState
                title="Something went wrong"
                message={this.state.error?.message ?? 'An unexpected error occurred'}
              />
            </SynPanel>
          </SynPageBody>
        </SynPage>
      )
    }

    return this.props.children
  }
}
