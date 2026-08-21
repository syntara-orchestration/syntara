import { Stack, StackItem } from '@patternfly/react-core'
import type { Approval } from '@syntara/contracts'

import { ApprovalNavigationHeader } from '../../components/ApprovalNavigationHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SidePanelHeader } from '../../components/SidePanelHeader'
import { ApprovalDetailContent } from '../approvals/ApprovalDetailContent'

import styles from './ApprovalSidePanel.module.css'

type ApprovalSidePanelProps = Readonly<{
  /** The approval object to display details for. */
  approval: Approval
  /** Optional message to display (e.g. the prompt from the approval node config). */
  message?: string
  /** Optional map of activity ID to human-readable name for resolving approval node names. */
  activityNameMap?: Map<string, string>
  /** Called when the close button is clicked. Should hide the panel without clearing the pending approval. */
  onClose: () => void
  /** Called after a decision (approve/reject) is successfully submitted. Used to dismiss the panel and clean up state. */
  onDecisionSubmitted: () => void
  /** Optional navigation handler for links within the panel (e.g. clicking the workflow name). Receives the target path. */
  onNavigate?: (path: string) => void
  /** Current approval index (0-based). Only shown when totalCount > 1. */
  currentIndex?: number
  /** Total number of pending approvals. Navigation controls only shown when > 1. */
  totalCount?: number
  /** Whether navigation to previous approval is available. */
  hasPrev?: boolean
  /** Whether navigation to next approval is available. */
  hasNext?: boolean
  /** Called when the previous button is clicked. */
  onNavigatePrev?: () => void
  /** Called when the next button is clicked. */
  onNavigateNext?: () => void
}>

/**
 * Right-side panel for reviewing an approval within the execution viewer.
 * Follows the same layout pattern as WorkflowHistoryCard:
 * fixed-width SynPanel with a header + scrollable body.
 *
 * When multiple approvals exist (totalCount > 1), shows navigation controls
 * to move between approvals without closing the panel.
 */
export function ApprovalSidePanel({
  approval,
  message,
  activityNameMap,
  onClose,
  onDecisionSubmitted,
  onNavigate,
  currentIndex,
  totalCount,
  hasPrev,
  hasNext,
  onNavigatePrev,
  onNavigateNext,
}: ApprovalSidePanelProps) {
  const showNavigation = totalCount !== undefined && totalCount > 1 && onNavigatePrev && onNavigateNext

  return (
    <SynPanel hasNoPadding isFullHeight className={styles.panel}>
      <div className={styles.panelInner}>
        <Stack className={styles.panelStack}>
          <StackItem className={styles.headerPadding}>
            {showNavigation ? (
              <ApprovalNavigationHeader
                title="Review approval"
                currentIndex={currentIndex}
                totalCount={totalCount}
                hasPrev={hasPrev}
                hasNext={hasNext}
                onNavigatePrev={onNavigatePrev}
                onNavigateNext={onNavigateNext}
                onClose={onClose}
                closeAriaLabel="Close approval panel"
              />
            ) : (
              <SidePanelHeader title="Review approval" onClose={onClose} closeAriaLabel="Close approval panel" />
            )}
          </StackItem>

          <StackItem isFilled className={styles.bodyPadding}>
            <ApprovalDetailContent
              key={approval.id}
              approval={approval}
              message={message}
              activityNameMap={activityNameMap}
              onDecisionSubmitted={onDecisionSubmitted}
              onWorkflowClick={onNavigate}
            />
          </StackItem>
        </Stack>
      </div>
    </SynPanel>
  )
}
