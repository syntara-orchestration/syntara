import { zodResolver } from '@hookform/resolvers/zod'
import { useCallback } from 'react'
import {
  useForm,
  type DefaultValues,
  type FieldValues,
  type Mode,
  type Resolver,
  type UseFormProps,
  type UseFormReturn,
} from 'react-hook-form'
import type { ZodType } from 'zod'

import { useFormMutationErrorHandler } from './useFormMutationErrorHandler'

/** Schema type accepted by `zodResolver` at the call site. */
type ZodResolverSchema = Parameters<typeof zodResolver>[0]

export type UseSynFormOptions<T extends FieldValues> = {
  /** Zod schema for client-side validation. Passed to `zodResolver` with `mode: 'sync'`. */
  schema: ZodType<T>
  /** Initial field values on first mount. */
  defaultValues: DefaultValues<T>
  /**
   * External values to keep the form in sync (RHF `values` prop). Use for edit
   * forms that hydrate from a query so fields do not flash empty before reset.
   */
  values?: T
  /** Passed through to RHF `useForm` when using the `values` prop (e.g. `keepDirtyValues`). */
  resetOptions?: UseFormProps<T>['resetOptions']
  /**
   * RHF validation trigger mode. Defaults to RHF's own default (`'onSubmit'`).
   * Use `'onBlur'` for forms that should surface field errors as the user tabs
   * away, ahead of a manual `trigger()` call (e.g. wizard step navigation).
   */
  mode?: Mode
  /** RHF re-validation mode (e.g. `onChange` for builder node editors). */
  reValidateMode?: Mode
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
 *   defaultValues: {
 *     name: group?.name ?? initialName ?? '',
 *     description: group?.description ?? '',
 *   },
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
  values,
  resetOptions,
  mode,
  reValidateMode,
  onClose,
}: UseSynFormOptions<T>): UseSynFormReturn<T> {
  const form = useForm<T>({
    resolver: zodResolver(schema as ZodResolverSchema, undefined, { mode: 'sync' }) as Resolver<T>,
    defaultValues,
    values,
    ...(resetOptions !== undefined ? { resetOptions } : {}),
    ...(mode !== undefined ? { mode } : {}),
    ...(reValidateMode !== undefined ? { reValidateMode } : {}),
  })

  const { reset, setError } = form

  const handleError = useFormMutationErrorHandler<T>(setError)

  const handleClose = useCallback(() => {
    reset()
    onClose?.()
  }, [reset, onClose])

  // Mutate the stable object RHF's useForm() returns instead of spreading into a
  // new object each render. useForm() keeps the same object reference across
  // renders (only formState is swapped in-place); spreading would return a new
  // object every render, which breaks RHF's read-tracking for formState fields
  // that are only ever read outside of render (e.g. inside an async submit
  // handler or a test's waitFor callback).
  return Object.assign(form, { handleError, handleClose })
}
