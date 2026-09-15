import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useWorkflowMetadata } from './useWorkflowMetadata'

describe('useWorkflowMetadata', () => {
  it('returns undefined when workflow is undefined', () => {
    const { result } = renderHook(() => useWorkflowMetadata(undefined))

    expect(result.current).toBeUndefined()
  })

  it('returns undefined when workflow has no name and no id', () => {
    const { result } = renderHook(() => useWorkflowMetadata({}))

    expect(result.current).toBeUndefined()
  })

  it('returns metadata with correct name, id, and version', () => {
    const { result } = renderHook(() =>
      useWorkflowMetadata({
        name: 'my-workflow',
        id: 'wf-123',
        current_version: 5,
        published_version_id: 'ver-2',
        created_by: 'admin',
      })
    )

    expect(result.current).toEqual({
      name: 'my-workflow',
      id: 'wf-123',
      version: 5,
      published: true,
      author: 'admin',
    })
  })

  it('uses current_version over version.version', () => {
    const { result } = renderHook(() =>
      useWorkflowMetadata({
        name: 'test',
        current_version: 10,
        version: { version: 3 },
      })
    )

    expect(result.current?.version).toBe(10)
  })

  it('falls back to version.version when current_version is missing', () => {
    const { result } = renderHook(() =>
      useWorkflowMetadata({
        name: 'test',
        version: { version: 7 },
      })
    )

    expect(result.current?.version).toBe(7)
  })

  it('falls back to 0 when no version info is provided', () => {
    const { result } = renderHook(() => useWorkflowMetadata({ name: 'test' }))

    expect(result.current?.version).toBe(0)
  })

  it('sets published to true when published_version_id is not null', () => {
    const { result } = renderHook(() => useWorkflowMetadata({ name: 'test', published_version_id: 'ver-1' }))

    expect(result.current?.published).toBe(true)
  })

  it('sets published to false when published_version_id is null', () => {
    const { result } = renderHook(() => useWorkflowMetadata({ name: 'test', published_version_id: null }))

    expect(result.current?.published).toBe(false)
  })

  it('sets published to false when published_version_id is undefined', () => {
    const { result } = renderHook(() => useWorkflowMetadata({ name: 'test' }))

    expect(result.current?.published).toBe(false)
  })

  it('uses created_by as author when it is a string', () => {
    const { result } = renderHook(() => useWorkflowMetadata({ name: 'test', created_by: 'jane' }))

    expect(result.current?.author).toBe('jane')
  })

  it('defaults author to Unknown when created_by is not a string', () => {
    const { result } = renderHook(() => useWorkflowMetadata({ name: 'test', created_by: 42 }))

    expect(result.current?.author).toBe('Unknown')
  })

  it('defaults author to Unknown when created_by is undefined', () => {
    const { result } = renderHook(() => useWorkflowMetadata({ name: 'test' }))

    expect(result.current?.author).toBe('Unknown')
  })

  it('defaults name to empty string when only id is provided', () => {
    const { result } = renderHook(() => useWorkflowMetadata({ id: 'wf-1' }))

    expect(result.current?.name).toBe('')
  })

  it('defaults id to empty string when only name is provided', () => {
    const { result } = renderHook(() => useWorkflowMetadata({ name: 'test' }))

    expect(result.current?.id).toBe('')
  })
})
