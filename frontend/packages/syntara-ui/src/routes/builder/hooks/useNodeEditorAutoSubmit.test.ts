import { act, renderHook } from '@testing-library/react'
import { type MutableRefObject, useRef } from 'react'
import { useForm, type ResolverResult } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'

import { useRegisterAutoSubmit } from './useNodeEditorAutoSubmit'

type TestFormData = { name: string }
type AutoSubmitFn = () => Promise<boolean>

function renderAutoSubmit(
  overrides: {
    defaultValues?: TestFormData
    resolver?: (values: TestFormData) => ResolverResult<TestFormData>
    onSubmit?: (data: TestFormData) => boolean | void | Promise<boolean | void>
  } = {}
) {
  const externalRef: { current: MutableRefObject<AutoSubmitFn | null> | null } = { current: null }

  const utils = renderHook(
    ({ onSubmit }) => {
      const ref = useRef<AutoSubmitFn | null>(null)
      const methods = useForm<TestFormData>({
        defaultValues: overrides.defaultValues ?? { name: 'test' },
        resolver: overrides.resolver,
      })
      useRegisterAutoSubmit(ref, methods, onSubmit)
      externalRef.current = ref
      return ref
    },
    { initialProps: { onSubmit: overrides.onSubmit ?? vi.fn() } }
  )

  return { ...utils, ref: externalRef as { current: MutableRefObject<AutoSubmitFn | null> } }
}

describe('useRegisterAutoSubmit', () => {
  it('registers an auto-submit function on the ref', () => {
    const { ref } = renderAutoSubmit()

    expect(ref.current.current).toBeInstanceOf(Function)
  })

  it('clears the ref on unmount', () => {
    const { ref, unmount } = renderAutoSubmit()

    expect(ref.current.current).toBeInstanceOf(Function)
    unmount()
    expect(ref.current.current).toBeNull()
  })

  it('calls onSubmit and returns true when validation passes', async () => {
    const onSubmit = vi.fn()
    const { ref } = renderAutoSubmit({ onSubmit })

    let succeeded: boolean | undefined
    await act(async () => {
      succeeded = await ref.current.current!()
    })

    expect(succeeded).toBe(true)
    expect(onSubmit).toHaveBeenCalledOnce()
    expect(onSubmit).toHaveBeenCalledWith({ name: 'test' })
  })

  it('returns false when validation fails', async () => {
    const onSubmit = vi.fn()
    const { ref } = renderAutoSubmit({
      defaultValues: { name: '' },
      resolver: (values: TestFormData): ResolverResult<TestFormData> => {
        if (!values.name) {
          return {
            values: {} as Record<string, never>,
            errors: { name: { type: 'required', message: 'Required' } },
          }
        }
        return { values, errors: {} as Record<string, never> }
      },
      onSubmit,
    })

    let succeeded: boolean | undefined
    await act(async () => {
      succeeded = await ref.current.current!()
    })

    expect(succeeded).toBe(false)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('uses the latest onSubmit callback after rerender', async () => {
    const firstCallback = vi.fn()
    const secondCallback = vi.fn()
    const { ref, rerender } = renderAutoSubmit({ onSubmit: firstCallback })

    rerender({ onSubmit: secondCallback })

    await act(async () => {
      await ref.current.current!()
    })

    expect(firstCallback).not.toHaveBeenCalled()
    expect(secondCallback).toHaveBeenCalledOnce()
  })

  it('awaits an async onSubmit before resolving', async () => {
    let released = false
    const onSubmit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          setTimeout(() => {
            released = true
            resolve()
          }, 20)
        })
    )
    const { ref } = renderAutoSubmit({ onSubmit })

    let succeeded: boolean | undefined
    await act(async () => {
      succeeded = await ref.current.current!()
    })

    expect(succeeded).toBe(true)
    expect(released).toBe(true)
    expect(onSubmit).toHaveBeenCalledOnce()
  })

  it('returns false when onSubmit returns false', async () => {
    const onSubmit = vi.fn(() => false)
    const { ref } = renderAutoSubmit({ onSubmit })

    let succeeded: boolean | undefined
    await act(async () => {
      succeeded = await ref.current.current!()
    })

    expect(succeeded).toBe(false)
    expect(onSubmit).toHaveBeenCalledOnce()
  })

  it('returns false when onSubmit throws', async () => {
    const onSubmit = vi.fn(() => {
      throw new Error('persist failed')
    })
    const { ref } = renderAutoSubmit({ onSubmit })

    let succeeded: boolean | undefined
    await act(async () => {
      succeeded = await ref.current.current!()
    })

    expect(succeeded).toBe(false)
    expect(onSubmit).toHaveBeenCalledOnce()
  })
})
