import {
  Button,
  Divider,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { SynSelect } from '../../../components/SynSelect'

import styles from './ToolsMultiSelect.module.css'

export type IntegrationWithTools = {
  id: string
  name: string
  discovered_tools: { id: string; name: string; description?: string | null }[]
}

export type ToolSelection = { strategy: 'ALL' } | { strategy: 'NONE' } | { strategy: 'SELECTED'; toolIds: string[] }

export type StaleToolInfo = {
  validToolIds: string[]
  removedCount: number
}

export type ToolsMultiSelectProps = {
  value: ToolSelection
  onChange: (selection: ToolSelection) => void
  integrations: IntegrationWithTools[]
  isLoading?: boolean
  isError?: boolean
  hasNoIntegrations?: boolean
  /** Called when tools finish loading and some selected tools are no longer available. */
  onStaleDetected?: (info: StaleToolInfo) => void
}

const INTEGRATION_PREFIX = 'integration:'
const ALL_TOOLS_VALUE = '__all_tools__'

type IntegrationValue = `${typeof INTEGRATION_PREFIX}${string}`

function integrationValue(id: string): IntegrationValue {
  return `${INTEGRATION_PREFIX}${id}`
}

function isIntegrationValue(val: unknown): val is IntegrationValue {
  return typeof val === 'string' && val.startsWith(INTEGRATION_PREFIX)
}

function toolDisplayName(namespacedName: string): string {
  const idx = namespacedName.indexOf('::')
  return idx >= 0 ? namespacedName.slice(idx + 2) : namespacedName
}

function selectionFromIds(ids: string[]): ToolSelection {
  return ids.length > 0 ? { strategy: 'SELECTED', toolIds: ids } : { strategy: 'NONE' }
}

type SelectionCtx = {
  value: ToolSelection
  selectedSet: Set<string>
  allToolIds: string[]
}

function applyIntegrationToggle(
  integrationId: string,
  integrations: IntegrationWithTools[],
  ctx: SelectionCtx,
  onChange: (s: ToolSelection) => void
): void {
  const integration = integrations.find((i) => i.id === integrationId)
  if (!integration) return
  const integrationToolIds = integration.discovered_tools.map((t) => t.id)
  const { value, selectedSet, allToolIds } = ctx

  if (value.strategy === 'ALL') {
    onChange(selectionFromIds(allToolIds.filter((id) => !integrationToolIds.includes(id))))
    return
  }

  const currentIds = value.strategy === 'SELECTED' ? value.toolIds : []
  const allSelected = integrationToolIds.length > 0 && integrationToolIds.every((id) => selectedSet.has(id))

  if (allSelected) {
    onChange(selectionFromIds(currentIds.filter((id) => !integrationToolIds.includes(id))))
  } else {
    const next = new Set(currentIds)
    integrationToolIds.forEach((id) => next.add(id))
    onChange({ strategy: 'SELECTED', toolIds: [...next] })
  }
}

function applyToolToggle(toolId: string, ctx: SelectionCtx, onChange: (s: ToolSelection) => void): void {
  const { value, selectedSet, allToolIds } = ctx
  if (value.strategy === 'ALL') {
    onChange(selectionFromIds(allToolIds.filter((id) => id !== toolId)))
    return
  }
  const currentIds = value.strategy === 'SELECTED' ? value.toolIds : []
  if (selectedSet.has(toolId)) {
    onChange(selectionFromIds(currentIds.filter((id) => id !== toolId)))
  } else {
    onChange({ strategy: 'SELECTED', toolIds: [...currentIds, toolId] })
  }
}

type ToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  isExpanded: boolean
  isDisabled: boolean
  label: string
  isLoading: boolean
  onToggle: () => void
  filterText: string
  onFilterChange: (val: string) => void
}>

function ToolsMenuToggle({
  toggleRef,
  isExpanded,
  isDisabled,
  label,
  isLoading,
  onToggle,
  filterText,
  onFilterChange,
}: ToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      isExpanded={isExpanded}
      isDisabled={isDisabled || isLoading}
      isFullWidth
      aria-label="Tools"
      onClick={onToggle}
    >
      <TextInputGroup isPlain isDisabled={isDisabled || isLoading}>
        <TextInputGroupMain
          value={isExpanded ? filterText : label}
          placeholder={isLoading ? 'Loading tools...' : 'Select tools'}
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          onChange={(_event, val) => onFilterChange(val)}
          autoComplete="off"
          id="tools-filter-input"
          aria-label="Select tools"
        />
        {isExpanded && filterText && (
          <TextInputGroupUtilities>
            <Button variant="plain" onClick={() => onFilterChange('')} aria-label="Clear filter">
              <RhUiCloseIcon />
            </Button>
          </TextInputGroupUtilities>
        )}
      </TextInputGroup>
    </MenuToggle>
  )
}

/**
 * A PatternFly Select dropdown for choosing which tools an AI Agent can call.
 *
 * "All tools" toggles the ALL strategy — every enabled tool is available,
 * including any added in the future. Individual tools and integration rows
 * switch to the SELECTED strategy with specific tool UUIDs. Clearing all
 * selections produces NONE.
 */
export function ToolsMultiSelect({
  value,
  onChange,
  integrations,
  isLoading = false,
  isError = false,
  hasNoIntegrations = false,
  onStaleDetected,
}: Readonly<ToolsMultiSelectProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterText, setFilterText] = useState('')

  const totalTools = useMemo(() => integrations.reduce((sum, i) => sum + i.discovered_tools.length, 0), [integrations])

  const staleFiredRef = useRef(false)
  useEffect(() => {
    if (isLoading || isError || staleFiredRef.current) return
    if (value.strategy !== 'SELECTED' || value.toolIds.length === 0) return
    const availableIds = new Set(integrations.flatMap((i) => i.discovered_tools.map((t) => t.id)))
    const validToolIds = value.toolIds.filter((id) => availableIds.has(id))
    const removedCount = value.toolIds.length - validToolIds.length
    if (removedCount === 0) return
    staleFiredRef.current = true
    onStaleDetected?.({ validToolIds, removedCount })
  }, [integrations, isLoading, isError, value, onStaleDetected])

  const filteredIntegrations = useMemo(() => {
    const query = filterText.toLowerCase().trim()
    if (!query) return integrations
    return integrations
      .map((integration) => {
        const nameMatches = integration.name.toLowerCase().includes(query)
        const matchingTools = nameMatches
          ? integration.discovered_tools
          : integration.discovered_tools.filter((t) => toolDisplayName(t.name).toLowerCase().includes(query))
        return { ...integration, discovered_tools: matchingTools }
      })
      .filter((i) => i.discovered_tools.length > 0)
  }, [integrations, filterText])

  // Flat list of all tool IDs — used when deselecting individual items from ALL
  const allToolIds = useMemo(() => integrations.flatMap((i) => i.discovered_tools.map((t) => t.id)), [integrations])

  const toggleLabel = useMemo(() => {
    if (hasNoIntegrations) return ''
    if (value.strategy === 'ALL') return 'All tools selected'
    if (value.strategy === 'NONE') return 'No tools selected'
    const count = value.toolIds.length
    if (count === 0) return 'No tools selected'
    return `${String(count)} of ${String(totalTools)} tools selected`
  }, [value, totalTools, hasNoIntegrations])

  // Set of explicitly selected IDs — only meaningful for SELECTED strategy
  const selectedSet = useMemo(() => new Set(value.strategy === 'SELECTED' ? value.toolIds : []), [value])

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, selectedValue: string | number | undefined) => {
      const val = String(selectedValue)
      const ctx: SelectionCtx = { value, selectedSet, allToolIds }
      if (val === ALL_TOOLS_VALUE) {
        onChange(value.strategy === 'ALL' ? { strategy: 'NONE' } : { strategy: 'ALL' })
      } else if (isIntegrationValue(val)) {
        applyIntegrationToggle(val.slice(INTEGRATION_PREFIX.length), integrations, ctx, onChange)
      } else {
        applyToolToggle(val, ctx, onChange)
      }
    },
    [integrations, selectedSet, value, onChange, allToolIds]
  )

  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <ToolsMenuToggle
        toggleRef={toggleRef}
        isExpanded={isOpen}
        isDisabled={isLoading}
        label={toggleLabel}
        isLoading={isLoading}
        onToggle={() => setIsOpen((prev) => !prev)}
        filterText={filterText}
        onFilterChange={setFilterText}
      />
    ),
    [isOpen, isLoading, toggleLabel, filterText]
  )

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open)
    if (!open) setFilterText('')
  }, [])

  const isFiltering = filterText.trim().length > 0

  return (
    <SynSelect
      id="agent-tools"
      isOpen={isOpen}
      onSelect={handleSelect}
      onOpenChange={handleOpenChange}
      toggle={renderToggle}
      isScrollable
      maxMenuHeight="400px"
      shouldFocusToggleOnSelect={false}
      aria-label="Tools"
      popperProps={{ position: 'start' }}
    >
      <SelectList aria-label="Tool options">
        {hasNoIntegrations && (
          <SelectOption isAriaDisabled value="__empty__">
            No MCP server integrations configured
          </SelectOption>
        )}
        {isFiltering && filteredIntegrations.length === 0 && (
          <SelectOption isAriaDisabled value="__no_results__">
            No results match &quot;{filterText}&quot;
          </SelectOption>
        )}
        {!hasNoIntegrations && !isFiltering && (
          <SelectOption hasCheckbox value={ALL_TOOLS_VALUE} isSelected={value.strategy === 'ALL'}>
            <strong>All tools</strong>
          </SelectOption>
        )}
        {totalTools > 0 && !isFiltering && <Divider component="li" />}
        {filteredIntegrations.map((integration) => {
          const integrationToolIds = integration.discovered_tools.map((t) => t.id)
          const allSelected =
            value.strategy === 'ALL' ||
            (integrationToolIds.length > 0 && integrationToolIds.every((id) => selectedSet.has(id)))
          return (
            <React.Fragment key={integration.id}>
              <SelectOption hasCheckbox value={integrationValue(integration.id)} isSelected={allSelected}>
                <strong>{integration.name}</strong> ({String(integration.discovered_tools.length)})
              </SelectOption>
              {integration.discovered_tools.map((tool) => (
                <SelectOption
                  key={tool.id}
                  hasCheckbox
                  value={tool.id}
                  isSelected={value.strategy === 'ALL' || selectedSet.has(tool.id)}
                  description={tool.description ?? undefined}
                  className={styles.toolOption}
                >
                  {toolDisplayName(tool.name)}
                </SelectOption>
              ))}
            </React.Fragment>
          )
        })}
      </SelectList>
    </SynSelect>
  )
}
