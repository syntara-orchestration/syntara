import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { z } from 'zod'

import { useSynForm } from './useSynForm'

vi.mock('./useFormMutationErrorHandler', () => ({
  useFormMutationErrorHandler: () => () => () => {
    /* noop */
  },
}))

const schema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
})

type FormData = z.infer<typeof schema>

const defaultValues: FormData = { name: '', description: '' }

describe('useSynForm', () => {
  it('returns RHF form methods', () => {
    const { result } = renderHook(() => useSynForm({ schema, defaultValues }))

    expect(typeof result.current.handleSubmit).toBe('function')
    expect(typeof result.current.control).toBe('object')
    expect(typeof result.current.reset).toBe('function')
    expect(typeof result.current.setError).toBe('function')
    expect(typeof result.current.watch).toBe('function')
    expect(typeof result.current.setValue).toBe('function')
  })

  it('returns handleClose and handleError', () => {
    const { result } = renderHook(() => useSynForm({ schema, defaultValues }))

    expect(typeof result.current.handleClose).toBe('function')
    expect(typeof result.current.handleError).toBe('function')
  })

  it('handleClose resets form and calls onClose', () => {
    const onClose = vi.fn()
    const { result } = renderHook(() => useSynForm({ schema, defaultValues, onClose }))

    act(() => {
      result.current.setValue('name', 'changed')
    })

    act(() => {
      result.current.handleClose()
    })

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(result.current.getValues('name')).toBe('')
  })

  it('handleClose works without onClose', () => {
    const { result } = renderHook(() => useSynForm({ schema, defaultValues }))

    expect(() => {
      act(() => {
        result.current.handleClose()
      })
    }).not.toThrow()
  })

  it('handleClose is stable across renders', () => {
    const onClose = vi.fn()
    const { result, rerender } = renderHook(() => useSynForm({ schema, defaultValues, onClose }))

    const firstHandleClose = result.current.handleClose
    rerender()

    expect(result.current.handleClose).toBe(firstHandleClose)
  })

  it('uses zodResolver — invalid submit does not call onValid', async () => {
    const onValid = vi.fn()
    const { result } = renderHook(() => useSynForm({ schema, defaultValues }))

    await act(async () => {
      await result.current.handleSubmit(onValid)()
    })

    expect(onValid).not.toHaveBeenCalled()
  })

  it('valid submit calls onValid with form data', async () => {
    const onValid = vi.fn()
    const { result } = renderHook(() => useSynForm({ schema, defaultValues }))

    act(() => {
      result.current.setValue('name', 'My Group')
    })

    await act(async () => {
      await result.current.handleSubmit(onValid)()
    })

    expect(onValid).toHaveBeenCalledOnce()
    expect(onValid.mock.calls[0][0]).toMatchObject({ name: 'My Group', description: '' })
  })
})
