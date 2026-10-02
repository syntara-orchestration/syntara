import { describe, expect, it } from 'vitest'

import { collectCatalogMatches, filterNodeOptions, type SearchableNodeOption } from './filterNodeOptions'

const options: SearchableNodeOption[] = [
  {
    id: 'action',
    label: 'Action',
    description: 'Execute scripts or make API calls',
    keywords: ['script', 'http'],
  },
  {
    id: 'terraform',
    label: 'Terraform Enterprise',
    description: 'Manage Terraform Enterprise workspaces, runs, GitHub App installs, and projects',
    keywords: ['terraform', 'tfe'],
    subtypes: [
      { id: 'tfe-create-workspace', label: 'Create Workspace', description: 'Create a TFE workspace' },
      { id: 'tfe-link-vcs', label: 'Link VCS to Workspace', description: 'Link a GitHub repo to a workspace' },
    ],
  },
]

describe('filterNodeOptions', () => {
  it('returns every option when the query is blank', () => {
    expect(filterNodeOptions(options, '   ')).toEqual(options)
  })

  it('matches a catalog label', () => {
    expect(filterNodeOptions(options, 'action').map((option) => option.label)).toEqual(['Action'])
  })

  it('filters action entries by label', () => {
    const actions = options[1]?.subtypes ?? []
    expect(filterNodeOptions(actions, 'create').map((option) => option.label)).toEqual(['Create Workspace'])
  })

  it('returns nothing when nothing matches', () => {
    expect(filterNodeOptions(options, 'nomatch')).toEqual([])
  })
})

describe('collectCatalogMatches', () => {
  it('returns category cards when the query is blank', () => {
    expect(collectCatalogMatches(options, '').map((match) => match.option.label)).toEqual([
      'Action',
      'Terraform Enterprise',
    ])
  })

  it('includes matching actions from a category on the catalog list', () => {
    const matches = collectCatalogMatches(options, 'github')
    expect(matches.map((match) => match.option.label)).toEqual(['Terraform Enterprise', 'Link VCS to Workspace'])
    expect(matches[1]).toMatchObject({ parentId: 'terraform', subtypeId: 'tfe-link-vcs' })
  })

  it('returns a nested action when only that action matches', () => {
    const matches = collectCatalogMatches(options, 'create workspace')
    expect(matches.map((match) => match.option.label)).toEqual(['Create Workspace'])
    expect(matches[0]?.subtypeId).toBe('tfe-create-workspace')
  })
})
