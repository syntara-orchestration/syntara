import {
  Alert,
  AlertActionLink,
  EmptyState,
  EmptyStateBody,
  Flex,
  FlexItem,
  Menu,
  MenuContent,
  MenuItem,
  MenuList,
  Modal,
  ModalBody,
  ModalHeader,
  SearchInput,
  Spinner,
} from '@patternfly/react-core'
import { RhUiSearchIcon } from '@patternfly/react-icons'
import { useRouterState } from '@tanstack/react-router'
import { useCallback, useMemo, useState } from 'react'

import { useUnsavedChanges } from '../../app/useUnsavedChanges'
import { useAlerts } from '../../providers/alerts'
import { usePendingBuilderNodeAddStore } from '../../routes/builder/pendingBuilderNodeAddStore'
import { SynLabel } from '../labels/SynLabel'

import styles from './CommandPalette.module.css'
import { COMMAND_PALETTE_RESULTS_ID, COMMAND_PALETTE_SEARCH_ID, commandPaletteOptionId } from './commandPaletteDom'
import { applyPaletteKey } from './commandPaletteKeyboard'
import type { CommandPaletteItem } from './commandPaletteTypes'
import { isWorkflowBuilderPath, resolveCommandPaletteChoice } from './resolveCommandPaletteChoice'
import { searchCommandPaletteItems } from './searchCommandPaletteItems'
import { useCommandPaletteItems } from './useCommandPaletteItems'

const READ_ONLY_STEP_ALERT = {
  title: 'Cannot add a step',
  description: 'This workflow is read-only. Open an editable workflow to add steps.',
} as const

export type CommandPaletteProps = {
  /** Whether the palette modal is visible. */
  isOpen: boolean
  /** Close the palette without navigating. */
  onClose: () => void
}

type ResultRowProps = Readonly<{
  item: CommandPaletteItem
  isActive: boolean
  onHighlight: () => void
}>

function setClippedTitle(el: HTMLElement, title: string) {
  if (el.scrollWidth > el.clientWidth) {
    el.title = title
  } else {
    el.removeAttribute('title')
  }
}

function CommandPaletteResultRow({ item, isActive, onHighlight }: ResultRowProps) {
  const optionId = commandPaletteOptionId(item.id)
  return (
    <MenuItem
      id={optionId}
      itemId={item.id}
      description={item.subtitle}
      isFocused={isActive}
      isSelected={isActive}
      onMouseEnter={onHighlight}
      aria-label={`${item.categoryLabel}: ${item.title}`}
    >
      <Flex className={styles.itemTitle} alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
        <FlexItem>
          <SynLabel>{item.categoryLabel}</SynLabel>
        </FlexItem>
        <FlexItem
          className={styles.itemTitleText}
          onMouseEnter={(event) => setClippedTitle(event.currentTarget, item.title)}
        >
          {item.title}
        </FlexItem>
      </Flex>
    </MenuItem>
  )
}

function paletteLiveStatus(args: {
  resultCount: number
  isLoading: boolean
  hasQuery: boolean
  hasError: boolean
}): string {
  if (args.resultCount === 0 && args.isLoading && args.hasQuery) return 'Loading search results'
  if (args.resultCount === 0 && args.hasQuery) return 'No results found'
  if (args.resultCount === 0) return 'Pages and steps. Type to search workflows, projects, and settings.'
  if (args.hasError) return `${args.resultCount} results. Some sources could not be loaded.`
  return `${args.resultCount} results`
}

type PaletteBodyProps = Readonly<{
  onClose: () => void
}>

function CommandPaletteBody({ onClose }: PaletteBodyProps) {
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(-1)
  const { items, isLoading, error, refetch } = useCommandPaletteItems(true)
  const { requestNavigation } = useUnsavedChanges()
  const { showError } = useAlerts()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const canAcceptStepAdd = usePendingBuilderNodeAddStore((state) => state.canAcceptStepAdd)
  const requestBuilderAdd = usePendingBuilderNodeAddStore((state) => state.request)

  const results = useMemo(() => searchCommandPaletteItems(items, query), [items, query])
  const highlightIndex = results.length === 0 || activeIndex < 0 ? -1 : Math.min(activeIndex, results.length - 1)
  const activeId = highlightIndex >= 0 ? results[highlightIndex]?.id : undefined

  const chooseItem = useCallback(
    (item: CommandPaletteItem) => {
      const choice = resolveCommandPaletteChoice(item, pathname)
      if (choice.builderAdd) {
        const blockedOnCanvas = isWorkflowBuilderPath(pathname) && canAcceptStepAdd === false
        const outcome = blockedOnCanvas ? 'rejected' : requestBuilderAdd(choice.builderAdd)
        if (outcome === 'rejected') {
          showError(READ_ONLY_STEP_ALERT)
          return
        }
      }
      onClose()
      if (choice.navigateTo) requestNavigation(choice.navigateTo)
    },
    [canAcceptStepAdd, onClose, pathname, requestBuilderAdd, requestNavigation, showError]
  )

  const handleQueryChange = (_event: React.FormEvent<HTMLInputElement>, value: string) => {
    setQuery(value)
    setActiveIndex(-1)
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    const { nextIndex, chosen } = applyPaletteKey(event.key, results, highlightIndex)
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex(nextIndex)
      return
    }
    if (event.key === 'Enter' && chosen) {
      event.preventDefault()
      chooseItem(chosen)
    }
  }

  const handleMenuSelect = (_event?: React.MouseEvent, itemId?: string | number) => {
    const selected = results.find((item) => item.id === itemId)
    if (selected) chooseItem(selected)
  }

  const hasQuery = query.trim().length > 0
  const showLoading = results.length === 0 && isLoading && hasQuery
  const showNoResults = results.length === 0 && !isLoading && hasQuery
  const liveStatus = paletteLiveStatus({
    resultCount: results.length,
    isLoading,
    hasQuery,
    hasError: Boolean(error),
  })

  return (
    <>
      <ModalHeader title="Search" description="Find pages, workflows, projects, settings, and steps." />
      <ModalBody onKeyDown={handleKeyDown}>
        <span className="pf-v6-u-screen-reader" role="status" aria-live="polite" aria-atomic="true">
          {liveStatus}
        </span>
        <SearchInput
          className={styles.search}
          searchInputId={COMMAND_PALETTE_SEARCH_ID}
          aria-label="Search pages, workflows, projects, settings, and steps"
          placeholder="Search pages, workflows, projects, settings, and steps"
          value={query}
          onChange={handleQueryChange}
          onClear={() => {
            setQuery('')
            setActiveIndex(-1)
          }}
          inputProps={{
            role: 'combobox',
            'aria-expanded': true,
            'aria-haspopup': 'listbox',
            'aria-controls': results.length > 0 ? COMMAND_PALETTE_RESULTS_ID : undefined,
            'aria-autocomplete': 'list',
            'aria-activedescendant': activeId ? commandPaletteOptionId(activeId) : undefined,
          }}
        />
        {error ? (
          <Alert
            isInline
            variant="danger"
            title={
              results.length > 0 ? 'Some search sources could not be loaded' : 'Search sources could not be loaded'
            }
            actionLinks={<AlertActionLink onClick={refetch}>Retry</AlertActionLink>}
          >
            {results.length > 0
              ? 'Results may be incomplete until those sources are available again.'
              : 'Try again, or search for a page or step that is already listed.'}
          </Alert>
        ) : null}
        {showLoading && (
          <Flex justifyContent={{ default: 'justifyContentCenter' }}>
            <FlexItem>
              <Spinner size="lg" aria-label="Loading search results" />
            </FlexItem>
          </Flex>
        )}
        {showNoResults && !error && (
          <EmptyState headingLevel="h2" titleText="No results found" icon={RhUiSearchIcon}>
            <EmptyStateBody>No pages, workflows, projects, settings, or steps match that search.</EmptyStateBody>
          </EmptyState>
        )}
        {results.length > 0 && (
          <Menu
            id={COMMAND_PALETTE_RESULTS_ID}
            isPlain
            isScrollable
            activeItemId={activeId}
            onSelect={handleMenuSelect}
            className={styles.results}
            role="listbox"
            aria-label="Search results"
          >
            <MenuContent maxMenuHeight="min(60vh, 28rem)">
              <MenuList>
                {results.map((item, index) => (
                  <CommandPaletteResultRow
                    key={item.id}
                    item={item}
                    isActive={index === highlightIndex}
                    onHighlight={() => setActiveIndex(index)}
                  />
                ))}
              </MenuList>
            </MenuContent>
          </Menu>
        )}
      </ModalBody>
    </>
  )
}

/**
 * Spotlight-style finder for pages, workflows, projects, settings, and builder
 * step types. Opened with Ctrl/Cmd+K.
 */
export function CommandPalette({ isOpen, onClose }: Readonly<CommandPaletteProps>) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      variant="medium"
      position="top"
      positionOffset="var(--pf-t--global--spacer--3xl)"
      aria-label="Search"
      elementToFocus={`#${COMMAND_PALETTE_SEARCH_ID}`}
    >
      {isOpen ? <CommandPaletteBody onClose={onClose} /> : null}
    </Modal>
  )
}
