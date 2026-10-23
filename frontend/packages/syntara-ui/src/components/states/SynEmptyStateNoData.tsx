import { Button, EmptyState, EmptyStateBody, EmptyStateActions, EmptyStateFooter } from '@patternfly/react-core'
import { PlusCircleIcon, RhUiAddIcon } from '@patternfly/react-icons'
import type { ReactNode } from 'react'

import { SynLink } from '../SynLink'

import { SynEmptyStateImageIcon } from './SynEmptyStateImageIcon'

/**
 * Full-height empty state for when there is no data available yet.
 *
 * @example
 * <SynEmptyStateNoData
 *   title="No workflows yet"
 *   description="Create your first workflow to get started."
 *   buttonText="Create workflow"
 *   linkTo="/create"
 * />
 */
type SynEmptyStateNoDataBaseProps = {
  title?: string
  description?: string
  buttonText?: string
  imageSrc?: string
  imageAlt?: string
  secondaryActions?: ReactNode
}

export type SynEmptyStateNoDataProps =
  /** Use a route link when the CTA navigates to another page. */
  | (SynEmptyStateNoDataBaseProps & { linkTo: string; addData?: never })
  /** Use an action callback for in-page actions such as opening a modal. */
  | (SynEmptyStateNoDataBaseProps & { linkTo?: never; addData?: () => void })

export function SynEmptyStateNoData(props: SynEmptyStateNoDataProps) {
  const { title, description, buttonText, imageSrc, imageAlt, linkTo, addData, secondaryActions } = props

  const defaultTitle = 'No data available'
  const defaultDescription = 'There is no data to display at this time.'
  const defaultButtonText = 'Add data'

  // Use custom image component if provided, otherwise use default icon
  const icon = imageSrc ? () => <SynEmptyStateImageIcon src={imageSrc} alt={imageAlt ?? 'No data'} /> : PlusCircleIcon

  return (
    <EmptyState headingLevel="h2" titleText={title ?? defaultTitle} icon={icon} isFullHeight>
      <EmptyStateBody>{description ?? defaultDescription}</EmptyStateBody>
      {(linkTo || addData) && (
        <EmptyStateFooter>
          <EmptyStateActions>
            {linkTo ? (
              <SynLink to={linkTo} variant="primary" icon={<RhUiAddIcon />}>
                {buttonText ?? defaultButtonText}
              </SynLink>
            ) : (
              <Button variant="primary" icon={<RhUiAddIcon />} onClick={addData}>
                {buttonText ?? defaultButtonText}
              </Button>
            )}
          </EmptyStateActions>
          {secondaryActions && <EmptyStateActions>{secondaryActions}</EmptyStateActions>}
        </EmptyStateFooter>
      )}
    </EmptyState>
  )
}
