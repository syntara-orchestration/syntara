import type { SettingsAPI, WorkflowAPI } from '@syntara/contracts'

import { AppRoute } from '../../app/AppRoute'
import type { TNavigationItem } from '../../app/navigationItems'
import type { ProjectRead } from '../../routes/access/types'
import type { NodeTypeDefinition } from '../../routes/builder/registry/NodeRegistry'

import {
  COMMAND_PALETTE_CATEGORY,
  COMMAND_PALETTE_CATEGORY_LABEL,
  type CommandPaletteItem,
} from './commandPaletteTypes'

type WorkflowRead = WorkflowAPI.components['schemas']['WorkflowRead']
type RuntimeSettingRead = SettingsAPI.components['schemas']['RuntimeSettingRead']

function isConcretePath(path: string): boolean {
  return !path.includes(':')
}

function mapNavigationItem(item: TNavigationItem, ancestors: readonly string[]): CommandPaletteItem | undefined {
  if (!isConcretePath(item.path)) return undefined

  return {
    id: `page:${item.path}:${item.label}`,
    category: COMMAND_PALETTE_CATEGORY.PAGE,
    categoryLabel: COMMAND_PALETTE_CATEGORY_LABEL[COMMAND_PALETTE_CATEGORY.PAGE],
    title: item.label,
    subtitle: ancestors.length > 0 ? ancestors.join(' › ') : undefined,
    keywords: [...ancestors],
    to: item.path,
    showWhenEmpty: true,
  }
}

/**
 * Flattens the permission-filtered nav tree into searchable page items.
 * Parameterized routes (`:id`) are skipped because they are not navigable
 * without a concrete resource.
 */
export function mapNavigationToCommandPaletteItems(
  items: readonly TNavigationItem[],
  ancestors: readonly string[] = []
): CommandPaletteItem[] {
  const mapped: CommandPaletteItem[] = []

  for (const item of items) {
    const pageItem = mapNavigationItem(item, ancestors)
    if (pageItem) mapped.push(pageItem)

    if (item.children?.length) {
      mapped.push(...mapNavigationToCommandPaletteItems(item.children, [...ancestors, item.label]))
    }
  }

  return mapped
}

export function mapProjectsToCommandPaletteItems(projects: readonly ProjectRead[]): CommandPaletteItem[] {
  return projects.map((project) => ({
    id: `project:${project.id}`,
    category: COMMAND_PALETTE_CATEGORY.PROJECT,
    categoryLabel: COMMAND_PALETTE_CATEGORY_LABEL[COMMAND_PALETTE_CATEGORY.PROJECT],
    title: project.name,
    subtitle: project.description ?? undefined,
    to: `${AppRoute.AccessManagement.Projects}/${project.id}`,
  }))
}

export function mapWorkflowsToCommandPaletteItems(workflows: readonly WorkflowRead[]): CommandPaletteItem[] {
  return workflows.map((workflow) => ({
    id: `workflow:${workflow.id}`,
    category: COMMAND_PALETTE_CATEGORY.WORKFLOW,
    categoryLabel: COMMAND_PALETTE_CATEGORY_LABEL[COMMAND_PALETTE_CATEGORY.WORKFLOW],
    title: workflow.name,
    subtitle: workflow.description ?? undefined,
    to: `/workflow-builder/${workflow.id}`,
  }))
}

export function mapSettingsToCommandPaletteItems(settings: readonly RuntimeSettingRead[]): CommandPaletteItem[] {
  return settings.map((setting) => ({
    id: `setting:${setting.key}`,
    category: COMMAND_PALETTE_CATEGORY.SETTING,
    categoryLabel: COMMAND_PALETTE_CATEGORY_LABEL[COMMAND_PALETTE_CATEGORY.SETTING],
    title: setting.name,
    subtitle: setting.description ?? setting.key,
    keywords: [setting.key, setting.category, setting.group ?? ''],
    to: `${AppRoute.SystemAdministration.Settings}/${setting.category}`,
  }))
}

function mapNodeType(node: NodeTypeDefinition): CommandPaletteItem[] {
  const parent: CommandPaletteItem = {
    id: `node:${node.id}`,
    category: COMMAND_PALETTE_CATEGORY.NODE,
    categoryLabel: COMMAND_PALETTE_CATEGORY_LABEL[COMMAND_PALETTE_CATEGORY.NODE],
    title: node.label,
    subtitle: node.description,
    keywords: node.keywords,
    to: AppRoute.WorkflowBuilder.New,
    showWhenEmpty: true,
  }

  const subtypes = (node.subtypes ?? []).map((subtype) => ({
    id: `node:${node.id}:${subtype.id}`,
    category: COMMAND_PALETTE_CATEGORY.NODE,
    categoryLabel: COMMAND_PALETTE_CATEGORY_LABEL[COMMAND_PALETTE_CATEGORY.NODE],
    title: subtype.label,
    subtitle: subtype.description ?? node.label,
    keywords: [...(node.keywords ?? []), ...(subtype.keywords ?? []), node.label],
    to: AppRoute.WorkflowBuilder.New,
    showWhenEmpty: true,
  }))

  return [parent, ...subtypes]
}

/** Node types and subtypes from the builder registry. */
export function mapNodesToCommandPaletteItems(nodes: readonly NodeTypeDefinition[]): CommandPaletteItem[] {
  return nodes.flatMap(mapNodeType)
}
