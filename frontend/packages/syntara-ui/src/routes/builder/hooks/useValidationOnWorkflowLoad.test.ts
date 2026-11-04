import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useValidationOnWorkflowLoad } from './useValidationOnWorkflowLoad'

function workflow(overrides: Record<string, unknown> = {}) {
  return {
    id: 'wf-1',
    current_version: 3,
    has_validation_issues: true,
    ...overrides,
  } as never
}

describe('useValidationOnWorkflowLoad', () => {
  const handleVerifySilent = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not verify for new workflows', () => {
    renderHook(() =>
      useValidationOnWorkflowLoad({
        isNew: true,
        workflow: workflow(),
        storeReady: true,
        handleVerifySilent,
      })
    )

    expect(handleVerifySilent).not.toHaveBeenCalled()
  })

  it('does not verify until the store is ready', () => {
    renderHook(() =>
      useValidationOnWorkflowLoad({
        isNew: false,
        workflow: workflow(),
        storeReady: false,
        handleVerifySilent,
      })
    )

    expect(handleVerifySilent).not.toHaveBeenCalled()
  })

  it('does not verify when has_validation_issues is not true', () => {
    renderHook(() =>
      useValidationOnWorkflowLoad({
        isNew: false,
        workflow: workflow({ has_validation_issues: false }),
        storeReady: true,
        handleVerifySilent,
      })
    )

    expect(handleVerifySilent).not.toHaveBeenCalled()
  })

  it('runs silent verify once per workflow version when validation issues are flagged', () => {
    const { rerender } = renderHook(
      (props: Parameters<typeof useValidationOnWorkflowLoad>[0]) => useValidationOnWorkflowLoad(props),
      {
        initialProps: {
          isNew: false,
          workflow: workflow(),
          storeReady: true,
          handleVerifySilent,
        },
      }
    )

    expect(handleVerifySilent).toHaveBeenCalledOnce()

    rerender({
      isNew: false,
      workflow: workflow(),
      storeReady: true,
      handleVerifySilent,
    })

    expect(handleVerifySilent).toHaveBeenCalledOnce()

    rerender({
      isNew: false,
      workflow: workflow({ current_version: 4 }),
      storeReady: true,
      handleVerifySilent,
    })

    expect(handleVerifySilent).toHaveBeenCalledTimes(2)
  })

  it('uses version.version when current_version is absent', () => {
    renderHook(() =>
      useValidationOnWorkflowLoad({
        isNew: false,
        workflow: workflow({ current_version: undefined, version: { version: 7 } }),
        storeReady: true,
        handleVerifySilent,
      })
    )

    expect(handleVerifySilent).toHaveBeenCalledOnce()
  })
})
