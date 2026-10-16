import { RhUiCheckCircleFillIcon, RhUiWarningFillIcon } from '@patternfly/react-icons'
import type { FormsAPI } from '@syntara/contracts'

import { SynLabel } from '../../../components/labels/SynLabel'
function formatFormResponseStatus(status: FormPromptStatus): string {
  if (status === 'expired') {
    return 'Timed out'
  }
  return status.charAt(0).toUpperCase() + status.slice(1)
}

type FormPromptStatus = FormsAPI.components['schemas']['FormPromptStatus']

const statusMap: Record<FormPromptStatus, 'info' | 'success' | 'danger' | 'warning'> = {
  pending: 'warning',
  submitted: 'success',
  expired: 'warning',
  cancelled: 'info',
}

const statusIcons: Record<FormPromptStatus, React.ComponentType<{ className?: string }>> = {
  pending: RhUiWarningFillIcon,
  submitted: RhUiCheckCircleFillIcon,
  expired: RhUiWarningFillIcon,
  cancelled: RhUiWarningFillIcon,
}

export function FormResponseStatusBadges(props: Readonly<{ status?: FormPromptStatus | null }>) {
  if (!props.status) {
    return null
  }

  const IconComponent = statusIcons[props.status]
  return (
    <SynLabel variant="outline" status={statusMap[props.status]} icon={<IconComponent />}>
      {formatFormResponseStatus(props.status)}
    </SynLabel>
  )
}
