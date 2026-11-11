import type { Query } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'

import {
  createApprovalsListPlaceholderData,
  getApprovalsListScopeKey,
  stripStaleListPaginationCursors,
} from './approvalsListPlaceholderData'

function mockQuery(path: string, projectId?: string): Pick<Query, 'queryKey'> {
  return {
    queryKey: [
      'get',
      path,
      projectId ? { params: { path: { project_id: projectId }, query: {} } } : { params: { query: {} } },
    ],
  }
}

describe('approvalsListPlaceholderData', () => {
  it('maps list scope keys for all projects vs a single project', () => {
    expect(getApprovalsListScopeKey(true, null)).toBe('all')
    expect(getApprovalsListScopeKey(false, 'proj-a')).toBe('project:proj-a')
  })

  it('keeps previous data within the same scope', () => {
    const placeholder = createApprovalsListPlaceholderData('all')
    const previous = { resources: [{ id: '1' }] }
    expect(placeholder(previous, mockQuery('/approvals') as Query)).toBe(previous)
  })

  it('drops previous data when the project scope changes', () => {
    const placeholder = createApprovalsListPlaceholderData('project:proj-b')
    const previous = { resources: [{ id: '1' }] }
    expect(placeholder(previous, mockQuery('/projects/{project_id}/approvals', 'proj-a') as Query)).toBeUndefined()
  })

  it('strips pagination cursors while placeholder data is active', () => {
    const data = { resources: [], next: 'cursor-next', prev: 'cursor-prev', total: 10 }
    expect(stripStaleListPaginationCursors(data, true)).toEqual({
      resources: [],
      next: null,
      prev: null,
      total: null,
    })
    expect(stripStaleListPaginationCursors(data, false)).toBe(data)
  })
})
