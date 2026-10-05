import { describe, expect, it } from 'vitest'

import {
  formResponseDefaultSort,
  formResponseTableColumns,
  FORM_RESPONSES_TABLE_DATA_COLUMN_COUNT,
} from './formResponseTableColumns'

describe('formResponseTableColumns', () => {
  it('includes workflow_name as a sortable column (requires GET /form_prompts sort=workflow_name on the API)', () => {
    const workflowColumn = formResponseTableColumns.find((col) => col.field === 'workflow_name')
    expect(workflowColumn).toEqual({ field: 'workflow_name', label: 'Workflow', isSortable: true })
  })

  it('defaults to newest created_at first', () => {
    expect(formResponseDefaultSort).toEqual({ field: 'created_at', direction: 'desc' })
  })

  it('exposes data column count for table layout', () => {
    expect(FORM_RESPONSES_TABLE_DATA_COLUMN_COUNT).toBe(formResponseTableColumns.length)
  })
})
