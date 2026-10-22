import { AppRoute } from '../../app/AppRoute'

import type { CommandPaletteItem } from './commandPaletteTypes'

export type CommandPaletteChoice = {
  /** Concrete path to navigate, or null when the current builder should stay open. */
  navigateTo: string | null
  /** Queued add-step request for the builder, if this hit is a step type. */
  builderAdd: NonNullable<CommandPaletteItem['builderAdd']> | null
}

export function isWorkflowBuilderPath(pathname: string): boolean {
  return pathname.startsWith('/workflow-builder/')
}

/**
 * Decide whether a palette hit should navigate, add a step to the open canvas,
 * or both (navigate to a new workflow, then open the add-step editor).
 */
export function resolveCommandPaletteChoice(item: CommandPaletteItem, pathname: string): CommandPaletteChoice {
  if (!item.builderAdd) {
    return { navigateTo: item.to, builderAdd: null }
  }

  if (isWorkflowBuilderPath(pathname)) {
    return { navigateTo: null, builderAdd: item.builderAdd }
  }

  return { navigateTo: AppRoute.WorkflowBuilder.New, builderAdd: item.builderAdd }
}
