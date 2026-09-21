import {
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
  Truncate,
} from '@patternfly/react-core'
import { RhUiSearchIcon } from '@patternfly/react-icons'
import { useRouterState } from '@tanstack/react-router'
import { useCallback, useMemo, useState } from 'react'

import { useUnsavedChanges } from '../../app/useUnsavedChanges'
import { usePendingBuilderNodeAddStore } from '../../routes/builder/pendingBuilderNodeAddStore'
import { SynLabel } from '../labels/SynLabel'

import styles from './CommandPalette.module.css'
import type { CommandPaletteItem } from './commandPaletteTypes'
import { resolveCommandPaletteChoice } from './resolveCommandPaletteChoice'
import { searchCommandPaletteItems } from './searchCommandPaletteItems'
import { useCommandPaletteItems } from './useCommandPaletteItems'

const SEARCH_INPUT_ID = 'command-palette-search'

export type CommandPaletteProps = {
  /** Whether the palette modal is visible. */
  isOpen: boolean
  /** Close the palette without navigating. */
  onClose: () => void
}

function applyPaletteKey(
  key: string,
  results: readonly CommandPaletteItem[],
  activeIndex: number
): { nextIndex: number; chosen: CommandPaletteItem | undefined } {
  if (results.length === 0) return { nextIndex: 0, chosen: undefined }

  if (key === 'ArrowDown') {
    return { nextIndex: (activeIndex + 1) % results.length, chosen: undefined }
  }
  if (key === 'ArrowUp') {
    return { nextIndex: (activeIndex - 1 + results.length) % results.length, chosen: undefined }
  }
  if (key === 'Enter') {
    return { nextIndex: activeIndex, chosen: results[activeIndex] }
  }
  return { nextIndex: activeIndex, chosen: undefined }
}

type ResultRowProps = Readonly<{
  item: CommandPaletteItem
  isActive: boolean
}>

function CommandPaletteResultRow({ item, isActive }: ResultRowProps) {
  return (
    <MenuItem
      itemId={item.id}
      description={item.subtitle}
      isFocused={isActive}
      aria-label={`${item.categoryLabel}: ${item.title}`}
    >
      <Flex className={styles.itemTitle} alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
        <FlexItem>
          <SynLabel>{item.categoryLabel}</SynLabel>
        </FlexItem>
        <FlexItem className={styles.itemTitleText}>
          <Truncate content={item.title} />
        </FlexItem>
      </Flex>
    </MenuItem>
  )
}

type PaletteBodyProps = Readonly<{
  onClose: () => void
}>

function CommandPaletteBody({ onClose }: PaletteBodyProps) {
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const { items, isLoading } = useCommandPaletteItems(true)
  const { requestNavigation } = useUnsavedChanges()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const queueBuilderAdd = usePendingBuilderNodeAddStore((state) => state.queue)

  const results = useMemo(() => searchCommandPaletteItems(items, query), [items, query])
  const clampedIndex = results.length === 0 ? 0 : Math.min(activeIndex, results.length - 1)
  const activeId = results[clampedIndex]?.id

  const chooseItem = useCallback(
    (item: CommandPaletteItem) => {
      const choice = resolveCommandPaletteChoice(item, pathname)
      onClose()
      if (choice.builderAdd) queueBuilderAdd(choice.builderAdd)
      if (choice.navigateTo) requestNavigation(choice.navigateTo)
    },
    [onClose, pathname, queueBuilderAdd, requestNavigation]
  )

  const handleQueryChange = (_event: React.FormEvent<HTMLInputElement>, value: string) => {
    setQuery(value)
    setActiveIndex(0)
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    const { nextIndex, chosen } = applyPaletteKey(event.key, results, clampedIndex)
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

  return (
    <>
      <ModalHeader title="Search" description="Find pages, workflows, projects, settings, and steps." />
      <ModalBody onKeyDown={handleKeyDown}>
        <SearchInput
          className={styles.search}
          searchInputId={SEARCH_INPUT_ID}
          aria-label="Search pages, workflows, projects, settings, and steps"
          placeholder="Search pages, workflows, projects, settings, and steps"
          value={query}
          onChange={handleQueryChange}
          onClear={() => {
            setQuery('')
            setActiveIndex(0)
          }}
        />
        {showLoading && (
          <Flex justifyContent={{ default: 'justifyContentCenter' }}>
            <FlexItem>
              <Spinner size="lg" aria-label="Loading search results" />
            </FlexItem>
          </Flex>
        )}
        {showNoResults && (
          <EmptyState headingLevel="h2" titleText="No results found" icon={RhUiSearchIcon}>
            <EmptyStateBody>No pages, workflows, projects, settings, or steps match that search.</EmptyStateBody>
          </EmptyState>
        )}
        {results.length > 0 && (
          <Menu
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
                  <CommandPaletteResultRow key={item.id} item={item} isActive={index === clampedIndex} />
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
export function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      variant="medium"
      position="top"
      positionOffset="var(--pf-t--global--spacer--3xl)"
      aria-label="Search"
      elementToFocus={`#${SEARCH_INPUT_ID}`}
    >
      {isOpen ? <CommandPaletteBody onClose={onClose} /> : null}
    </Modal>
  )
}
