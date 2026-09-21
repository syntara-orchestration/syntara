import { describe, expect, it, vi } from 'vitest'

import { AppRoute } from '../../app/AppRoute'
import type { TNavigationItem } from '../../app/navigationItems'
import type { ProjectRead } from '../../routes/access/types'
import type { NodeTypeDefinition } from '../../routes/builder/registry/NodeRegistry'

import { COMMAND_PALETTE_CATEGORY } from './commandPaletteTypes'
import {
  mapNavigationToCommandPaletteItems,
  mapNodesToCommandPaletteItems,
  mapProjectsToCommandPaletteItems,
  mapSettingsToCommandPaletteItems,
  mapWorkflowsToCommandPaletteItems,
} from './mapCommandPaletteItems'

const DummyIcon = () => null

function makeNode(overrides: Partial<NodeTypeDefinition> = {}): NodeTypeDefinition {
  return {
    id: 'action',
    label: 'Action',
    icon: DummyIcon,
    description: 'Run a script or API call',
    keywords: ['http', 'script'],
    formComponent: DummyIcon,
    onSubmit: vi.fn(),
    ...overrides,
  }
}

describe('mapNavigationToCommandPaletteItems', () => {
  const nav: TNavigationItem[] = [
    {
      label: 'Workflows',
      path: AppRoute.Workflows.Root,
    },
    {
      label: 'Configuration',
      path: AppRoute.Configuration.Integrations.Root,
      children: [
        { label: 'Integrations', path: AppRoute.Configuration.Integrations.Root },
        { label: 'Edit Integration', path: AppRoute.Configuration.Integrations.Edit, hidden: true },
      ],
    },
    {
      label: 'Edit Workflow',
      path: AppRoute.WorkflowBuilder.Edit,
      hidden: true,
    },
  ]

  it('includes concrete paths and parent breadcrumbs', () => {
    const items = mapNavigationToCommandPaletteItems(nav)

    expect(items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          category: COMMAND_PALETTE_CATEGORY.PAGE,
          title: 'Workflows',
          to: '/workflows',
          showWhenEmpty: true,
        }),
        expect.objectContaining({
          title: 'Integrations',
          subtitle: 'Configuration',
          to: '/configuration/integrations',
        }),
      ])
    )
  })

  it('skips parameterized routes', () => {
    const items = mapNavigationToCommandPaletteItems(nav)
    expect(items.some((item) => item.to.includes(':'))).toBe(false)
    expect(items.some((item) => item.title === 'Edit Workflow')).toBe(false)
    expect(items.some((item) => item.title === 'Edit Integration')).toBe(false)
  })
})

describe('mapProjectsToCommandPaletteItems', () => {
  it('maps each project to its detail route', () => {
    const projects: ProjectRead[] = [
      {
        id: 'p1',
        name: 'Platform',
        description: 'Shared services',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]

    expect(mapProjectsToCommandPaletteItems(projects)).toEqual([
      expect.objectContaining({
        id: 'project:p1',
        category: COMMAND_PALETTE_CATEGORY.PROJECT,
        title: 'Platform',
        subtitle: 'Shared services',
        to: '/system-administration/access-management/projects/p1',
      }),
    ])
  })
})

describe('mapWorkflowsToCommandPaletteItems', () => {
  it('maps each workflow to the builder edit route', () => {
    const items = mapWorkflowsToCommandPaletteItems([
      {
        id: 'wf-1',
        name: 'Deploy app',
        description: 'Production deploy',
        current_version: 1,
        is_enabled: true,
        project_id: 'p1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ])

    expect(items).toEqual([
      expect.objectContaining({
        id: 'workflow:wf-1',
        category: COMMAND_PALETTE_CATEGORY.WORKFLOW,
        title: 'Deploy app',
        to: '/workflow-builder/wf-1',
      }),
    ])
  })
})

describe('mapSettingsToCommandPaletteItems', () => {
  it('maps settings onto their category tab', () => {
    const items = mapSettingsToCommandPaletteItems([
      {
        id: 's1',
        key: 'workflow_engine.max_depth',
        name: 'Max depth',
        description: 'Nesting cap',
        helper_text: null,
        depends_on: null,
        category: 'workflow_execution',
        group: 'Execution',
        value: 5,
        default_value: 5,
        effective_value: 5,
        value_type: 'integer',
        requires_restart: false,
        cache_ttl_seconds: null,
        validation_schema: null,
        version: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ])

    expect(items[0]).toEqual(
      expect.objectContaining({
        id: 'setting:workflow_engine.max_depth',
        category: COMMAND_PALETTE_CATEGORY.SETTING,
        title: 'Max depth',
        keywords: ['workflow_engine.max_depth', 'workflow_execution', 'Execution'],
        to: '/system-administration/settings/workflow_execution',
      })
    )
  })
})

describe('mapNodesToCommandPaletteItems', () => {
  it('includes the parent type and each subtype', () => {
    const items = mapNodesToCommandPaletteItems([
      makeNode({
        subtypes: [
          {
            id: 'action-api',
            label: 'REST API',
            icon: DummyIcon,
            description: 'Call an HTTP endpoint',
            keywords: ['rest'],
          },
        ],
      }),
    ])

    expect(items).toHaveLength(2)
    expect(items[0]).toEqual(
      expect.objectContaining({
        id: 'node:action',
        title: 'Action',
        to: AppRoute.WorkflowBuilder.New,
        showWhenEmpty: true,
      })
    )
    expect(items[1]).toEqual(
      expect.objectContaining({
        id: 'node:action:action-api',
        title: 'REST API',
      })
    )
    expect(items[1]?.keywords).toEqual(expect.arrayContaining(['http', 'rest', 'Action']))
  })
})
