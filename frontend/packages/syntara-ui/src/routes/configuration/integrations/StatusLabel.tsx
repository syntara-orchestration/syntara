import { Tooltip } from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiCloseCircleIcon, RhUiMinusCircleIcon, RhUiSyncIcon } from '@patternfly/react-icons'
import { IntegrationStatusEnum } from '@syntara/contracts'

import { SynLabel } from '../../../components/labels/SynLabel'

type IntegrationStatus = (typeof IntegrationStatusEnum)[keyof typeof IntegrationStatusEnum]

const statusMap: Record<IntegrationStatus, 'success' | 'danger' | 'custom'> = {
  [IntegrationStatusEnum.UNKNOWN]: 'custom',
  [IntegrationStatusEnum.AVAILABLE]: 'success',
  [IntegrationStatusEnum.ERROR]: 'danger',
  [IntegrationStatusEnum.VALIDATING]: 'custom',
}

const statusIcons: Record<IntegrationStatus, React.ComponentType<{ className?: string }>> = {
  [IntegrationStatusEnum.UNKNOWN]: RhUiMinusCircleIcon,
  [IntegrationStatusEnum.AVAILABLE]: RhUiCheckCircleIcon,
  [IntegrationStatusEnum.ERROR]: RhUiCloseCircleIcon,
  [IntegrationStatusEnum.VALIDATING]: RhUiSyncIcon,
}

type StatusLabelProps = Readonly<{
  status: string
  errorMessage?: string | null
}>

export function StatusLabel({ status, errorMessage }: StatusLabelProps) {
  const integrationStatus = status as IntegrationStatus
  const Icon = statusIcons[integrationStatus] || RhUiCloseCircleIcon
  const labelStatus = statusMap[integrationStatus] || 'custom'
  const capitalizedStatus = status.charAt(0).toUpperCase() + status.slice(1)

  const hasTooltip = integrationStatus === IntegrationStatusEnum.ERROR && errorMessage

  const label = (
    <SynLabel variant="outline" status={labelStatus} icon={<Icon />} tabIndex={hasTooltip ? 0 : undefined}>
      {capitalizedStatus}
    </SynLabel>
  )

  if (hasTooltip) {
    return <Tooltip content={errorMessage}>{label}</Tooltip>
  }

  return label
}
