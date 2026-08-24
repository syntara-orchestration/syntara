import { EmptyState, EmptyStateBody } from '@patternfly/react-core'
import { RhUiErrorFillIcon } from '@patternfly/react-icons'

export type SynEmptyStateServiceUnavailableProps = {
  title?: string
  description?: string
  showAdminHint?: boolean
}

/**
 * Display for 503 Service Unavailable errors.
 *
 * @example
 * if (error.error === 'service_unavailable') {
 *   return <SynEmptyStateServiceUnavailable description={error.message} />
 * }
 */
export function SynEmptyStateServiceUnavailable(props: Readonly<SynEmptyStateServiceUnavailableProps>) {
  const { title, description, showAdminHint = true } = props

  const defaultTitle = 'Service Unavailable'
  const defaultDescription = 'The AI service is currently unavailable. This may be a configuration issue.'
  const adminHint = 'If this persists, contact your system administrator.'

  const fullDescription = showAdminHint
    ? `${description ?? defaultDescription} ${adminHint}`
    : (description ?? defaultDescription)

  return (
    <EmptyState headingLevel="h2" titleText={title ?? defaultTitle} icon={RhUiErrorFillIcon} isFullHeight>
      <EmptyStateBody>{fullDescription}</EmptyStateBody>
    </EmptyState>
  )
}
