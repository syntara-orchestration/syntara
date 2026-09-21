import { describe, expect, it } from 'vitest'

import { COMMAND_PALETTE_CATEGORY, COMMAND_PALETTE_MAX_RESULTS, type CommandPaletteItem } from './commandPaletteTypes'
import { searchCommandPaletteItems } from './searchCommandPaletteItems'

function item(overrides: Partial<CommandPaletteItem> & Pick<CommandPaletteItem, 'id' | 'title'>): CommandPaletteItem {
  return {
    category: COMMAND_PALETTE_CATEGORY.PAGE,
    categoryLabel: 'Pages',
    to: `/${overrides.id}`,
    ...overrides,
  }
}

const catalog: CommandPaletteItem[] = [
  item({ id: 'page-workflows', title: 'Workflows', showWhenEmpty: true }),
  item({
    id: 'node-http',
    title: 'REST API',
    category: COMMAND_PALETTE_CATEGORY.NODE,
    categoryLabel: 'Steps',
    keywords: ['http', 'api'],
    showWhenEmpty: true,
  }),
  item({
    id: 'wf-deploy',
    title: 'Deploy production',
    category: COMMAND_PALETTE_CATEGORY.WORKFLOW,
    categoryLabel: 'Workflows',
    subtitle: 'Roll out the app',
  }),
  item({
    id: 'project-platform',
    title: 'Platform',
    category: COMMAND_PALETTE_CATEGORY.PROJECT,
    categoryLabel: 'Projects',
  }),
  item({
    id: 'setting-depth',
    title: 'Max depth',
    category: COMMAND_PALETTE_CATEGORY.SETTING,
    categoryLabel: 'Settings',
    keywords: ['workflow_engine.max_depth'],
  }),
]

describe('searchCommandPaletteItems', () => {
  it('returns only showWhenEmpty items when the query is blank', () => {
    const results = searchCommandPaletteItems(catalog, '  ')

    expect(results.map((result) => result.id)).toEqual(['page-workflows', 'node-http'])
  })

  it('fuzzy-matches titles across every loaded source', () => {
    const results = searchCommandPaletteItems(catalog, 'deploy')

    expect(results.some((result) => result.id === 'wf-deploy')).toBe(true)
  })

  it('matches keywords such as http on step types', () => {
    const results = searchCommandPaletteItems(catalog, 'http')

    expect(results[0]?.id).toBe('node-http')
  })

  it('matches setting keys', () => {
    const results = searchCommandPaletteItems(catalog, 'max_depth')

    expect(results.some((result) => result.id === 'setting-depth')).toBe(true)
  })

  it('returns an empty list when nothing matches', () => {
    expect(searchCommandPaletteItems(catalog, 'qwertyuiopasdfgh')).toEqual([])
  })

  it('caps the result list', () => {
    const many = Array.from({ length: COMMAND_PALETTE_MAX_RESULTS + 10 }, (_, index) =>
      item({ id: `page-${index}`, title: `Page ${index}`, showWhenEmpty: true })
    )

    expect(searchCommandPaletteItems(many, '').length).toBe(COMMAND_PALETTE_MAX_RESULTS)
    expect(searchCommandPaletteItems(many, 'Page').length).toBe(COMMAND_PALETTE_MAX_RESULTS)
  })
})
