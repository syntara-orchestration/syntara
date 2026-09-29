import { MenuToggle, SelectList, SelectOption, Spinner } from '@patternfly/react-core'
import type React from 'react'
import { useCallback, useMemo, useState } from 'react'

import { SynSelect } from '../../../components/SynSelect'

import { useAllEnabledMcpIntegrations } from './useAllEnabledMcpIntegrations'
import { useMcpIntegrationTools } from './useMcpIntegrationTools'

const EMPTY_OPTION_VALUE = '__empty__'

function SelectToggle({
  id,
  toggleRef,
  label,
  ariaLabel,
  isOpen,
  isDisabled,
  isLoading,
  isError,
  onToggle,
}: Readonly<{
  id?: string
  toggleRef: React.Ref<HTMLButtonElement>
  label: string
  ariaLabel: string
  isOpen: boolean
  isDisabled?: boolean
  isLoading: boolean
  isError: boolean
  onToggle: () => void
}>) {
  return (
    <MenuToggle
      id={id}
      ref={toggleRef}
      onClick={onToggle}
      isExpanded={isOpen}
      isDisabled={isDisabled || isLoading}
      isFullWidth
      status={isError ? 'danger' : undefined}
      aria-label={ariaLabel}
    >
      {isLoading ? <Spinner size="sm" aria-label={`Loading ${ariaLabel}`} /> : label}
    </MenuToggle>
  )
}

export type McpServerSelectProps = Readonly<{
  id?: string
  value?: string
  onChange: (integrationId: string) => void
  isDisabled?: boolean
  /** Scopes integrations to those global or assigned to this project. */
  projectId?: string
}>

/** Select limited to enabled `mcp_server` integrations. */
export function McpServerSelect({ id, value, onChange, isDisabled, projectId }: McpServerSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const { integrations, isLoading, isError } = useAllEnabledMcpIntegrations(projectId)

  const selected = useMemo(() => integrations.find((integration) => integration.id === value), [integrations, value])

  const toggleLabel = useMemo(() => {
    if (isError) return 'Error loading MCP server integrations'
    return selected?.name ?? 'Select an MCP server integration'
  }, [isError, selected?.name])

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, selectedValue: string | number | undefined) => {
      if (typeof selectedValue !== 'string' || selectedValue === EMPTY_OPTION_VALUE) return
      setIsOpen(false)
      onChange(selectedValue)
    },
    [onChange]
  )

  const renderToggle = useCallback(
    (toggleRef: React.Ref<HTMLButtonElement>) => (
      <SelectToggle
        id={id}
        toggleRef={toggleRef}
        label={toggleLabel}
        ariaLabel="MCP server integration"
        isOpen={isOpen}
        isDisabled={isDisabled}
        isLoading={isLoading}
        isError={isError}
        onToggle={() => setIsOpen((prev) => !prev)}
      />
    ),
    [id, toggleLabel, isOpen, isDisabled, isLoading, isError]
  )

  return (
    <SynSelect isOpen={isOpen} onOpenChange={setIsOpen} onSelect={handleSelect} toggle={renderToggle}>
      <SelectList aria-label="MCP server integration options">
        {integrations.map((integration) => (
          <SelectOption key={integration.id} value={integration.id} isSelected={integration.id === value}>
            {integration.name}
          </SelectOption>
        ))}
        {integrations.length === 0 && !isLoading && (
          <SelectOption isDisabled value={EMPTY_OPTION_VALUE}>
            {isError ? 'Failed to load MCP server integrations' : 'No MCP server integrations available'}
          </SelectOption>
        )}
      </SelectList>
    </SynSelect>
  )
}

export type McpToolNameSelectProps = Readonly<{
  id?: string
  integrationId?: string
  value?: string
  onChange: (toolName: string) => void
  isDisabled?: boolean
}>

/** Select populated from the chosen integration's discovered tools. */
export function McpToolNameSelect({ id, integrationId, value, onChange, isDisabled }: McpToolNameSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const { tools, isLoading, isError } = useMcpIntegrationTools(integrationId)

  const toggleLabel = useMemo(() => {
    if (!integrationId) return 'Select an MCP server integration first'
    if (isError) return 'Error loading tools'
    if (!value) return 'Select a tool'
    return value
  }, [integrationId, isError, value])

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, selectedValue: string | number | undefined) => {
      if (typeof selectedValue !== 'string' || selectedValue === EMPTY_OPTION_VALUE) return
      setIsOpen(false)
      onChange(selectedValue)
    },
    [onChange]
  )

  const renderToggle = useCallback(
    (toggleRef: React.Ref<HTMLButtonElement>) => (
      <SelectToggle
        id={id}
        toggleRef={toggleRef}
        label={toggleLabel}
        ariaLabel="Tool"
        isOpen={isOpen}
        isDisabled={isDisabled || !integrationId}
        isLoading={isLoading}
        isError={isError}
        onToggle={() => setIsOpen((prev) => !prev)}
      />
    ),
    [id, toggleLabel, isOpen, isDisabled, integrationId, isLoading, isError]
  )

  return (
    <SynSelect isOpen={isOpen} onOpenChange={setIsOpen} onSelect={handleSelect} toggle={renderToggle}>
      <SelectList aria-label="Tool options">
        {tools.map((tool) => (
          <SelectOption
            key={tool.id ?? tool.name}
            value={tool.name}
            isSelected={tool.name === value}
            description={tool.description ?? undefined}
          >
            {tool.name}
          </SelectOption>
        ))}
        {tools.length === 0 && !isLoading && (
          <SelectOption isDisabled value={EMPTY_OPTION_VALUE}>
            {isError ? 'Failed to load tools' : 'No tools discovered on this integration'}
          </SelectOption>
        )}
      </SelectList>
    </SynSelect>
  )
}
