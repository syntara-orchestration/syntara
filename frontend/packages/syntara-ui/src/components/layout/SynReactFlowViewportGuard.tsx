import { Stack, StackItem } from '@patternfly/react-core'
import { useNavigate } from '@tanstack/react-router'
import type { ReactNode } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { panelContentStackStyle } from '../../app/panelContentStackStyle'
import { detachPromise } from '../../utils/detachPromise'
import { SynEmptyStateViewportTooSmall } from '../states/SynEmptyStateViewportTooSmall'

import styles from './SynReactFlowViewportGuard.module.css'

type SynReactFlowViewportGuardProps = {
  children: ReactNode
  /** Callback when user clicks the return button in the empty state. Defaults to navigating to Workflows. */
  onReturn?: () => void
}

/** Hides page content and shows a full-page empty state when the viewport width is below 1024px (nav bar remains visible). Height is not gated. */
export function SynReactFlowViewportGuard({ children, onReturn }: SynReactFlowViewportGuardProps) {
  const navigate = useNavigate()
  const handleReturn = onReturn ?? (() => detachPromise(navigate({ to: AppRoute.Workflows.Root })))

  return (
    <Stack style={panelContentStackStyle}>
      <StackItem isFilled className={styles.content}>
        <Stack hasGutter style={panelContentStackStyle}>
          {children}
        </Stack>
      </StackItem>
      <StackItem isFilled className={styles.emptyState} data-testid="viewport-guard-empty-state">
        <SynEmptyStateViewportTooSmall onReturn={handleReturn} />
      </StackItem>
    </Stack>
  )
}
