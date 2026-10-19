import { Stack, StackItem } from '@patternfly/react-core'
import type { ReactNode } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { panelContentStackStyle } from '../../app/panelContentStackStyle'
import { SynEmptyStateViewportTooSmall } from '../states/SynEmptyStateViewportTooSmall'

import styles from './SynReactFlowViewportGuard.module.css'

type SynReactFlowViewportGuardProps = {
  children: ReactNode
  /** Route for the return link in the empty state. Defaults to Workflows. */
  returnTo?: string
}

/** Hides page content and shows a full-page empty state when the viewport width is below 1024px (nav bar remains visible). Height is not gated. */
export function SynReactFlowViewportGuard({
  children,
  returnTo = AppRoute.Workflows.Root,
}: SynReactFlowViewportGuardProps) {
  return (
    <Stack style={panelContentStackStyle}>
      <StackItem isFilled className={styles.content}>
        <Stack hasGutter style={panelContentStackStyle}>
          {children}
        </Stack>
      </StackItem>
      <StackItem isFilled className={styles.emptyState} data-testid="viewport-guard-empty-state">
        <SynEmptyStateViewportTooSmall returnTo={returnTo} />
      </StackItem>
    </Stack>
  )
}
