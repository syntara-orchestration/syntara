import { describe, expect, it } from 'vitest'

import { getAAPSelectionStaleness, type AAPStalenessBrowser } from './aapSelectionStaleness'

const ORGANIZATIONS = [
  { id: 1, name: 'Org 1' },
  { id: 2, name: 'Org 2' },
]
const TEMPLATES = [
  { id: 10, name: 'Template 1', description: null },
  { id: 11, name: 'Template 2', description: null },
]

function createBrowser(overrides: Partial<AAPStalenessBrowser> = {}): AAPStalenessBrowser {
  return {
    isActive: true,
    error: null,
    loadingOrgs: false,
    loadingTemplates: false,
    organizations: ORGANIZATIONS,
    templates: TEMPLATES,
    ...overrides,
  }
}

const SELECTIONS = { selectedOrganization: 'Org 1', selectedTemplateName: 'Template 1' }

describe('getAAPSelectionStaleness', () => {
  it('reports nothing when both selections are present in the loaded lists', () => {
    expect(getAAPSelectionStaleness(createBrowser(), SELECTIONS)).toEqual({ organization: false, template: false })
  })

  it('reports a stale organization and suppresses the template flag for the cascade', () => {
    const staleness = getAAPSelectionStaleness(createBrowser(), {
      selectedOrganization: 'Gone Org',
      selectedTemplateName: 'Gone Template',
    })

    expect(staleness).toEqual({ organization: true, template: false })
  })

  it('reports a stale template while the organization stays valid', () => {
    const staleness = getAAPSelectionStaleness(createBrowser(), {
      ...SELECTIONS,
      selectedTemplateName: 'Gone Template',
    })

    expect(staleness).toEqual({ organization: false, template: true })
  })

  it('reports nothing while lists are loading', () => {
    const staleness = getAAPSelectionStaleness(createBrowser({ loadingOrgs: true, loadingTemplates: true }), {
      selectedOrganization: 'Gone Org',
      selectedTemplateName: 'Gone Template',
    })

    expect(staleness).toEqual({ organization: false, template: false })
  })

  it('reports nothing when a query has errored', () => {
    const staleness = getAAPSelectionStaleness(createBrowser({ error: new Error('upstream unavailable') }), {
      selectedOrganization: 'Gone Org',
      selectedTemplateName: 'Template 1',
    })

    expect(staleness).toEqual({ organization: false, template: false })
  })

  it('reports nothing while browsing is inactive', () => {
    const staleness = getAAPSelectionStaleness(createBrowser({ isActive: false }), {
      selectedOrganization: 'Gone Org',
      selectedTemplateName: 'Template 1',
    })

    expect(staleness).toEqual({ organization: false, template: false })
  })

  it('reports nothing when no selection is present', () => {
    const staleness = getAAPSelectionStaleness(createBrowser(), {
      selectedOrganization: undefined,
      selectedTemplateName: undefined,
    })

    expect(staleness).toEqual({ organization: false, template: false })
  })

  it('treats empty-string selections as absent', () => {
    const staleness = getAAPSelectionStaleness(createBrowser(), {
      selectedOrganization: '',
      selectedTemplateName: '',
    })

    expect(staleness).toEqual({ organization: false, template: false })
  })
})
