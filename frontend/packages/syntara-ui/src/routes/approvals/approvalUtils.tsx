import { RhUiDislikeFillIcon, RhUiLikeFillIcon, RhUiWarningFillIcon } from '@patternfly/react-icons'
import type { ApprovalStatus } from '@syntara/contracts'

import { SynLabel } from '../../components/labels/SynLabel'

const statusMap: Record<ApprovalStatus, 'info' | 'success' | 'danger' | 'warning'> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
  expired: 'warning',
  cancelled: 'info',
}

const statusIcons: Record<ApprovalStatus, React.ComponentType<{ className?: string }>> = {
  pending: RhUiWarningFillIcon,
  approved: RhUiLikeFillIcon,
  rejected: RhUiDislikeFillIcon,
  expired: RhUiWarningFillIcon,
  cancelled: RhUiWarningFillIcon,
}

export function ApprovalStatusBadges(props: Readonly<{ status?: ApprovalStatus | null }>) {
  if (!props.status) {
    return null
  }

  const IconComponent = statusIcons[props.status]
  const capitalizedStatus = props.status.charAt(0).toUpperCase() + props.status.slice(1)

  return (
    <SynLabel variant="outline" status={statusMap[props.status]} icon={<IconComponent />}>
      {capitalizedStatus}
    </SynLabel>
  )
}
