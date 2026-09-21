import { describe, expect, it } from 'vitest'

import { AppRoute } from '../../app/AppRoute'

import { COMMAND_PALETTE_CATEGORY, type CommandPaletteItem } from './commandPaletteTypes'
import { isWorkflowBuilderPath, resolveCommandPaletteChoice } from './resolveCommandPaletteChoice'

const pageItem: CommandPaletteItem = {
  id: 'page:workflows',
  category: COMMAND_PALETTE_CATEGORY.PAGE,
  categoryLabel: 'Pages',
  title: 'Workflows',
  to: '/workflows',
}

const stepItem: CommandPaletteItem = {
  id: 'node:trigger:trigger-manual',
  category: COMMAND_PALETTE_CATEGORY.NODE,
  categoryLabel: 'Steps',
  title: 'Manual trigger',
  to: AppRoute.WorkflowBuilder.New,
  builderAdd: { nodeTypeId: 'trigger', nodeSubtypeId: 'trigger-manual' },
}

describe('isWorkflowBuilderPath', () => {
  it('matches new and existing builder routes', () => {
    expect(isWorkflowBuilderPath('/workflow-builder/new')).toBe(true)
    expect(isWorkflowBuilderPath('/workflow-builder/wf-1')).toBe(true)
    expect(isWorkflowBuilderPath('/workflows')).toBe(false)
  })
})

describe('resolveCommandPaletteChoice', () => {
  it('navigates pages without a builder add', () => {
    expect(resolveCommandPaletteChoice(pageItem, '/workflow-builder/wf-1')).toEqual({
      navigateTo: '/workflows',
      builderAdd: null,
    })
  })

  it('adds a step on the open canvas instead of creating a new workflow', () => {
    expect(resolveCommandPaletteChoice(stepItem, '/workflow-builder/wf-1')).toEqual({
      navigateTo: null,
      builderAdd: { nodeTypeId: 'trigger', nodeSubtypeId: 'trigger-manual' },
    })
  })

  it('queues a step and opens a new builder when not already on the canvas', () => {
    expect(resolveCommandPaletteChoice(stepItem, '/workflows')).toEqual({
      navigateTo: AppRoute.WorkflowBuilder.New,
      builderAdd: { nodeTypeId: 'trigger', nodeSubtypeId: 'trigger-manual' },
    })
  })
})
