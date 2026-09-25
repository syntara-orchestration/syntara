import { useMemo } from 'react'

import { useFilteredNavigationItems } from '../../app/useFilteredNavigationItems'
import { useCanI } from '../../hooks/useCanI'
import { useAllProjects } from '../../routes/access/useAllProjects'
import { NodeRegistry } from '../../routes/builder/registry/NodeRegistry'
import { useAllSettings } from '../../routes/configuration/settings/useAllSettings'
import { useAllWorkflows } from '../../routes/workflows/useAllWorkflows'

import type { CommandPaletteItem } from './commandPaletteTypes'
import {
  mapNavigationToCommandPaletteItems,
  mapNodesToCommandPaletteItems,
  mapProjectsToCommandPaletteItems,
  mapSettingsToCommandPaletteItems,
  mapWorkflowsToCommandPaletteItems,
} from './mapCommandPaletteItems'

export type CommandPaletteCatalog = {
  items: CommandPaletteItem[]
  isLoading: boolean
}

/**
 * Loads every command-palette source.
 *
 * To add a future catalog (credentials, users, executions, …):
 * 1. Write a `mapXToCommandPaletteItems` mapper next to the others.
 * 2. Call its `useAllX({ enabled })` (or equivalent) hook here.
 * 3. Concatenate `items` in the `useMemo` below.
 *
 * Remote sources are fetched only while the palette is open (`enabled`) so
 * idle sessions do not pay the pagination cost. React Query caches the lists
 * for subsequent opens.
 */
export function useCommandPaletteItems(enabled: boolean): CommandPaletteCatalog {
  const navItems = useFilteredNavigationItems()
  const { projects, isLoading: projectsLoading } = useAllProjects({ enabled })
  const { workflows, isLoading: workflowsLoading } = useAllWorkflows({ enabled })
  const { allowed: canReadSettings } = useCanI('read', 'setting', { enabled })
  const { settings, isLoading: settingsLoading } = useAllSettings({ enabled: enabled && canReadSettings })

  const pageItems = useMemo(() => mapNavigationToCommandPaletteItems(navItems), [navItems])
  const projectItems = useMemo(() => mapProjectsToCommandPaletteItems(projects), [projects])
  const workflowItems = useMemo(() => mapWorkflowsToCommandPaletteItems(workflows), [workflows])
  const settingItems = useMemo(() => mapSettingsToCommandPaletteItems(settings), [settings])
  const nodeItems = useMemo(() => mapNodesToCommandPaletteItems(NodeRegistry.getAll()), [])

  const items = useMemo(
    () => [...pageItems, ...nodeItems, ...projectItems, ...workflowItems, ...settingItems],
    [pageItems, nodeItems, projectItems, workflowItems, settingItems]
  )

  const isLoading = projectsLoading || workflowsLoading || settingsLoading

  return { items, isLoading }
}
