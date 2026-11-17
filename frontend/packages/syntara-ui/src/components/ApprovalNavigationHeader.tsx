import { Button, Content, ContentVariants, Flex, FlexItem, Icon, Title, TitleSizes } from '@patternfly/react-core'
import { RhUiCaretLeftIcon, RhUiCaretRightIcon, RhUiCloseIcon } from '@patternfly/react-icons'
import type { ReactNode } from 'react'

import styles from './ApprovalNavigationHeader.module.css'

type ApprovalNavigationHeaderProps = Readonly<{
  /** The title text displayed in the panel header. */
  title: string
  /** Current approval index (0-based). Only shown when totalCount > 1. */
  currentIndex?: number
  /** Total number of approvals. Navigation controls only shown when > 1. */
  totalCount?: number
  /** Whether navigation to previous approval is available. */
  hasPrev?: boolean
  /** Whether navigation to next approval is available. */
  hasNext?: boolean
  /** Called when the previous button is clicked. */
  onNavigatePrev?: () => void
  /** Called when the next button is clicked. */
  onNavigateNext?: () => void
  /** Called when the close button is clicked. */
  onClose: () => void
  /** Accessible label for the close button. Defaults to `"Close"`. */
  closeAriaLabel?: string
  /** Accessible label for the previous navigation button. Defaults to `"Previous approval"`. */
  navigatePrevAriaLabel?: string
  /** Accessible label for the next navigation button. Defaults to `"Next approval"`. */
  navigateNextAriaLabel?: string
  /** Optional icon rendered before the title. */
  icon?: ReactNode
}>

/**
 * Enhanced side panel header with approval navigation controls.
 * Shows "Approval X of Y" counter and Previous/Next buttons when multiple approvals exist.
 * Supports keyboard navigation (ArrowLeft/ArrowRight).
 * Falls back to standard SidePanelHeader behavior when navigation props are omitted.
 */
export function ApprovalNavigationHeader({
  title,
  currentIndex,
  totalCount,
  hasPrev = false,
  hasNext = false,
  onNavigatePrev,
  onNavigateNext,
  onClose,
  closeAriaLabel = 'Close',
  navigatePrevAriaLabel = 'Previous approval',
  navigateNextAriaLabel = 'Next approval',
  icon,
}: ApprovalNavigationHeaderProps) {
  const showNavigation = totalCount !== undefined && totalCount > 1 && onNavigatePrev && onNavigateNext

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!showNavigation) return

    if (event.key === 'ArrowLeft' && hasPrev) {
      event.preventDefault()
      onNavigatePrev()
    } else if (event.key === 'ArrowRight' && hasNext) {
      event.preventDefault()
      onNavigateNext()
    }
  }

  return (
    <Flex
      justifyContent={{ default: 'justifyContentSpaceBetween' }}
      alignItems={{ default: 'alignItemsFlexStart' }}
      tabIndex={showNavigation ? 0 : undefined}
      onKeyDown={handleKeyDown}
    >
      <FlexItem>
        <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
          {icon && <FlexItem>{icon}</FlexItem>}
          <FlexItem>
            <Title headingLevel="h2" size={TitleSizes.md}>
              {title}
              {showNavigation && currentIndex !== undefined && (
                <>
                  {' '}
                  <Content component={ContentVariants.small} className={styles.counter}>
                    ({currentIndex + 1} of {totalCount})
                  </Content>
                </>
              )}
            </Title>
          </FlexItem>
        </Flex>
      </FlexItem>

      <FlexItem>
        <Flex gap={{ default: 'gapSm' }}>
          {showNavigation && (
            <>
              <FlexItem>
                <Button
                  variant="plain"
                  aria-label={navigatePrevAriaLabel}
                  isAriaDisabled={!hasPrev}
                  onClick={hasPrev ? onNavigatePrev : undefined}
                >
                  <Icon>
                    <RhUiCaretLeftIcon />
                  </Icon>
                </Button>
              </FlexItem>
              <FlexItem>
                <Button
                  variant="plain"
                  aria-label={navigateNextAriaLabel}
                  isAriaDisabled={!hasNext}
                  onClick={hasNext ? onNavigateNext : undefined}
                >
                  <Icon>
                    <RhUiCaretRightIcon />
                  </Icon>
                </Button>
              </FlexItem>
            </>
          )}
          <FlexItem>
            <Button variant="plain" onClick={onClose} aria-label={closeAriaLabel}>
              <Icon>
                <RhUiCloseIcon />
              </Icon>
            </Button>
          </FlexItem>
        </Flex>
      </FlexItem>
    </Flex>
  )
}
