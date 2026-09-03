import { EmptyState, EmptyStateBody } from '@patternfly/react-core'
import { RhUiLockIcon } from '@patternfly/react-icons'

/**
 * Standardized "Access denied" empty state for pages the user lacks permission to view.
 *
 * @example
 * <SynEmptyStateAccessDenied description="You don't have permission to view settings." />
 */
export type SynEmptyStateAccessDeniedProps = Readonly<{
  /** Explains what the user cannot access and how to request it. */
  description: string
}>

export function SynEmptyStateAccessDenied({ description }: SynEmptyStateAccessDeniedProps) {
  return (
    <EmptyState headingLevel="h2" titleText="Access denied" icon={RhUiLockIcon} isFullHeight>
      <EmptyStateBody>{description}</EmptyStateBody>
    </EmptyState>
  )
}
