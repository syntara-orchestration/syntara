import type { IntegrationsAPI, ToolManagerAPI } from '@syntara/contracts'
import { useCallback, useMemo } from 'react'
import type { Control, UseFormSetValue } from 'react-hook-form'
import { useWatch } from 'react-hook-form'

import type { AIAgentFormData } from './aiAgentFormSchema'
import type { IntegrationWithTools, ToolSelection } from './ToolsMultiSelect'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']
type ToolWithParameters = ToolManagerAPI.components['schemas']['ToolWithParameters']

export type StaleToolInfo = {
  validToolIds: string[]
  removedCount: number
}

export function groupToolsByIntegration(
  tools: ToolWithParameters[],
  integrations: IntegrationRead[]
): IntegrationWithTools[] {
  const integrationMap = new Map(
    integrations.filter((i): i is IntegrationRead & { id: string } => Boolean(i.id)).map((i) => [i.id, i.name])
  )

  const grouped = new Map<string, { name: string; tools: { id: string; name: string; description: string | null }[] }>()
  for (const tool of tools) {
    const integrationId = tool.integration_id
    if (!integrationId || !integrationMap.has(integrationId) || tool.enabled === false || !tool.id) continue
    if (!grouped.has(integrationId)) {
      grouped.set(integrationId, { name: integrationMap.get(integrationId) ?? integrationId, tools: [] })
    }
    grouped.get(integrationId)?.tools.push({
      id: tool.id,
      name: tool.namespaced_name,
      description: null,
    })
  }

  return Array.from(grouped.entries()).map(([id, { name, tools: discovered_tools }]) => ({
    id,
    name,
    discovered_tools,
  }))
}

export function getToolSelection(strategy: string | undefined, toolIds: string[] | undefined): ToolSelection {
  if (strategy === 'ALL') return { strategy: 'ALL' }
  if (strategy === 'SELECTED' && toolIds?.length) return { strategy: 'SELECTED', toolIds }
  return { strategy: 'NONE' }
}

function findStaleToolInfo(selection: ToolSelection, integrations: IntegrationWithTools[]): StaleToolInfo | null {
  if (selection.strategy !== 'SELECTED') return null
  const availableIds = new Set(
    integrations.flatMap((integration) => integration.discovered_tools.map((tool) => tool.id))
  )
  const validToolIds = selection.toolIds.filter((id) => availableIds.has(id))
  const removedCount = selection.toolIds.length - validToolIds.length
  return removedCount > 0 ? { validToolIds, removedCount } : null
}

export function formatStaleToolsWarning(removedCount: number | undefined): string {
  if (!removedCount) return ''
  const isPlural = removedCount > 1
  return `${String(removedCount)} previously selected tool${isPlural ? 's are' : ' is'} no longer available and ${isPlural ? 'have' : 'has'} been removed.`
}

export function getVisibleToolSelection(
  selection: ToolSelection,
  integrations: IntegrationWithTools[],
  isLoading: boolean,
  isError: boolean
): { selection: ToolSelection; staleToolInfo: StaleToolInfo | null } {
  const staleToolInfo = isLoading || isError ? null : findStaleToolInfo(selection, integrations)
  return {
    selection: staleToolInfo ? getToolSelection('SELECTED', staleToolInfo.validToolIds) : selection,
    staleToolInfo,
  }
}

export function cleanStaleToolSelections(
  data: AIAgentFormData,
  integrations: IntegrationWithTools[],
  isLoading: boolean,
  isError: boolean
): AIAgentFormData {
  if (isLoading || isError || data.tool_selection_strategy !== 'SELECTED') return data

  const availableIds = new Set(
    integrations.flatMap((integration) => integration.discovered_tools.map((tool) => tool.id))
  )
  const currentToolSelections = data.tool_selections ?? []
  const toolSelections = currentToolSelections.filter((id) => availableIds.has(id))
  if (toolSelections.length === currentToolSelections.length) return data

  return {
    ...data,
    tool_selection_strategy: toolSelections.length > 0 ? 'SELECTED' : 'NONE',
    tool_selections: toolSelections,
    ...(toolSelections.length === 0 ? { integration_connections: [] } : {}),
  }
}

export function useToolSelection(control: Control<AIAgentFormData>, setValue: UseFormSetValue<AIAgentFormData>) {
  const toolSelectionStrategy = useWatch({ control, name: 'tool_selection_strategy' }) ?? 'NONE'
  const rawToolSelections = useWatch({ control, name: 'tool_selections' })

  const toolSelection = useMemo<ToolSelection>(() => {
    const toolSelections = rawToolSelections ?? []
    if (toolSelectionStrategy === 'ALL') return { strategy: 'ALL' }
    if (toolSelectionStrategy === 'SELECTED' && toolSelections.length > 0)
      return { strategy: 'SELECTED', toolIds: toolSelections }
    return { strategy: 'NONE' }
  }, [toolSelectionStrategy, rawToolSelections])

  const handleToolSelectionChange = useCallback(
    (selection: ToolSelection) => {
      if (selection.strategy === 'ALL') {
        setValue('tool_selection_strategy', 'ALL')
        setValue('tool_selections', [])
      } else if (selection.strategy === 'SELECTED') {
        setValue('tool_selection_strategy', 'SELECTED')
        setValue('tool_selections', selection.toolIds)
      } else {
        setValue('tool_selection_strategy', 'NONE')
        setValue('tool_selections', [])
        setValue('integration_connections', [])
      }
    },
    [setValue]
  )

  return { toolSelection, handleToolSelectionChange }
}
