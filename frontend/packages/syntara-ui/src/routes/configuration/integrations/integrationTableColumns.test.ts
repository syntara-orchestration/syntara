import { describe, expect, it } from 'vitest'

import { integrationDefaultSort, integrationTableColumns } from './integrationTableColumns'

describe('integrationTableColumns', () => {
  it('defines sortable name, status, type, and state columns', () => {
    expect(integrationTableColumns).toEqual([
      { field: 'name', label: 'Server name / ID', isSortable: true },
      { field: 'validation_status', label: 'Status', isSortable: true },
      { field: 'integration_type', label: 'Integration type', isSortable: true },
      { field: 'api_url', label: 'API URL' },
      { field: 'enabled_resources', label: 'Enabled resources' },
      { field: 'last_validated_at', label: 'Last checked', isSortable: true },
      { field: 'enabled', label: 'State', isSortable: true },
    ])
  })

  it('defaults to name ascending', () => {
    expect(integrationDefaultSort).toEqual({ field: 'name', direction: 'asc' })
  })
})
