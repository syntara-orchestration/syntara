import { zodResolver } from '@hookform/resolvers/zod'
import { useCallback } from 'react'
import { useForm, type DefaultValues, type FieldValues, type Resolver, type UseFormReturn } from 'react-hook-form'
import type { ZodType } from 'zod'

import { useFormMutationErrorHandler } from './useFormMutationErrorHandler'

/** Schema type accepted by `zodResolver` at the call site. */
type ZodResolverSchema = Parameters<typeof zodResolver>[0]

export type UseSynFormOptions<T extends FieldValues> = {
  /** Zod schema for client-side validation. Passed to `zodResolver` with `mode: 'sync'`. */
  schema: ZodType<T>
  /** Initial field values on first mount. */
  defaultValues: DefaultValues<T>
  /** Called after `reset()` when `handleClose` is invoked. */
  onClose?: () => void
}

export type UseSynFormReturn<T extends FieldValues> = UseFormReturn<T> & {
  /**
   * Pre-bound error handler factory for mutation `onError` callbacks:
   *
   * ```tsx
   * mutate(body, { onError: handleError({ title: 'Failed to create group' }) })
   * ```
   *
   * Maps FastAPI 422 field errors onto RHF field state and shows an alert toast.
   */
  handleError: ReturnType<typeof useFormMutationErrorHandler<T>>
  /** Resets the form to `defaultValues` and calls `onClose`. */
  handleClose: () => void
}

/**
 * Encapsulates the standard form modal setup:
 * `useForm` + `zodResolver(schema, undefined, { mode: 'sync' })` +
 * `useFormMutationErrorHandler` + `handleClose`.
 *
 * Returns the full `UseFormReturn<T>` so `control`, `watch`, `setValue`,
 * `register`, etc. remain accessible without indirection.
 *
 * Pair with `SynForm` so fields can omit `control`:
 *
 * ```tsx
 * const form = useSynForm({ schema, defaultValues, onClose })
 * const { handleSubmit, handleClose, reset } = form
 *
 * <Form onSubmit={handleSubmit(onSubmit)}>
 *   <SynForm form={form}>
 *     <SynTextField name="name" label="Name" isRequired />
 *   </SynForm>
 * </Form>
 * ```
 *
 * Reset-on-open is intentionally left to the consumer's `useEffect` because
 * the exact dependencies vary per modal (e.g. `[isOpen, item, reset]`). The
 * `reset` function returned here is stable per react-hook-form guarantees.
 *
 * @example
 * ```tsx
 * const form = useSynForm({
 *   schema: groupFormSchema,
 *   defaultValues: { name: '', description: '' },
 *   onClose,
 * })
 * const { handleSubmit, handleClose, reset } = form
 *
 * useEffect(() => {
 *   if (isOpen) reset({ name: group?.name ?? '', description: group?.description ?? '' })
 * }, [isOpen, group, reset])
 *
 * <Form onSubmit={handleSubmit(onSubmit)}>
 *   <SynForm form={form}>
 *     <SynTextField name="name" label="Group name" isRequired />
 *   </SynForm>
 * </Form>
 * ```
 */
export function useSynForm<T extends FieldValues>({
  schema,
  defaultValues,
  onClose,
}: UseSynFormOptions<T>): UseSynFormReturn<T> {
  const form = useForm<T>({
    resolver: zodResolver(schema as ZodResolverSchema, undefined, { mode: 'sync' }) as Resolver<T>,
    defaultValues,
  })

  const { reset, setError } = form

  const handleError = useFormMutationErrorHandler<T>(setError)

  const handleClose = useCallback(() => {
    reset()
    onClose?.()
  }, [reset, onClose])

  return { ...form, handleError, handleClose }
}
