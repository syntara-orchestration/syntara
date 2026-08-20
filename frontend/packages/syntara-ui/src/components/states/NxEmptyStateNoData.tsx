import { Button, EmptyState, EmptyStateBody, EmptyStateActions, EmptyStateFooter } from '@patternfly/react-core'
import { PlusCircleIcon } from '@patternfly/react-icons'
import type { ReactNode } from 'react'

import { NxEmptyStateImageIcon } from './NxEmptyStateImageIcon'

/**
 * Full-height empty state for when there is no data available yet.
 *
 * @example
 * <NxEmptyStateNoData
 *   title="No workflows yet"
 *   description="Create your first workflow to get started."
 *   buttonText="Create Workflow"
 *   addData={() => navigate('/create')}
 * />
 */
export type NxEmptyStateNoDataProps = {
  title?: string
  description?: string
  buttonText?: string
  imageSrc?: string
  imageAlt?: string
  addData?: () => void
  secondaryActions?: ReactNode
}

export function NxEmptyStateNoData(props: NxEmptyStateNoDataProps) {
  const { title, description, buttonText, imageSrc, imageAlt, addData, secondaryActions } = props

  const defaultTitle = 'No data available'
  const defaultDescription = 'There is no data to display at this time.'
  const defaultButtonText = 'Add data'

  // Use custom image component if provided, otherwise use default icon
  const icon = imageSrc ? () => <NxEmptyStateImageIcon src={imageSrc} alt={imageAlt ?? 'No data'} /> : PlusCircleIcon

  return (
    <EmptyState headingLevel="h2" titleText={title ?? defaultTitle} icon={icon} isFullHeight>
      <EmptyStateBody>{description ?? defaultDescription}</EmptyStateBody>
      {addData && (
        <EmptyStateFooter>
          <EmptyStateActions>
            <Button variant="primary" onClick={addData}>
              {buttonText ?? defaultButtonText}
            </Button>
          </EmptyStateActions>
          {secondaryActions && <EmptyStateActions>{secondaryActions}</EmptyStateActions>}
        </EmptyStateFooter>
      )}
    </EmptyState>
  )
}
