import { RhUiWarningFillIcon } from '@patternfly/react-icons'

import { SynLabel } from '../../components/labels/SynLabel'

type ApprovalPendingBadgeProps = {
  approvalPending?: boolean
}

/**
 * Badge component that displays "Pending approval" when approvalPending is true.
 * Used to indicate that an execution has one or more approval activities in WAITING status.
 */
export function ApprovalPendingBadge({ approvalPending }: Readonly<ApprovalPendingBadgeProps>) {
  if (!approvalPending) return null

  return (
    <SynLabel variant="outline" status="warning" icon={<RhUiWarningFillIcon />}>
      Pending approval
    </SynLabel>
  )
}
