import { Button, EmptyState, EmptyStateBody, EmptyStateActions, EmptyStateFooter } from '@patternfly/react-core'
import { RhUiSearchIcon } from '@patternfly/react-icons'

import { SynEmptyStateImageIcon } from './SynEmptyStateImageIcon'

/**
 * Full-height empty state for when filters return no results.
 *
 * @example
 * <SynEmptyStateFilter
 *   clearAllFilters={() => setSearch('')}
 *   imageSrc="/no-results.png"
 *   imageAlt="No results"
 * />
 */
export type SynEmptyStateFilterProps = {
  title?: string
  description?: string
  buttonText?: string
  imageSrc?: string
  imageAlt?: string
  clearAllFilters?: () => void
}

export function SynEmptyStateFilter(props: SynEmptyStateFilterProps) {
  const { title, description, buttonText, imageSrc, imageAlt, clearAllFilters } = props

  const defaultTitle = 'No results found'
  const defaultDescription = 'No results match the filter criteria. Try changing your filter settings.'
  const defaultButtonText = 'Clear all filters'

  // Use custom image component if provided, otherwise use default icon
  const icon = imageSrc
    ? () => <SynEmptyStateImageIcon src={imageSrc} alt={imageAlt ?? 'No results'} />
    : RhUiSearchIcon

  return (
    <EmptyState headingLevel="h2" titleText={title ?? defaultTitle} icon={icon} isFullHeight>
      <EmptyStateBody>{description ?? defaultDescription}</EmptyStateBody>
      {clearAllFilters && (
        <EmptyStateFooter>
          <EmptyStateActions>
            <Button variant="link" onClick={clearAllFilters}>
              {buttonText ?? defaultButtonText}
            </Button>
          </EmptyStateActions>
        </EmptyStateFooter>
      )}
    </EmptyState>
  )
}
