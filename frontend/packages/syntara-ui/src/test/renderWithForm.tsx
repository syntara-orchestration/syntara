import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import type { DefaultValues, FieldValues, UseFormReturn } from 'react-hook-form'
import type { ZodType } from 'zod'

import { RenderWithFormWrapper } from './renderWithFormWrapper'

/**
 * Test helper: renders a component that depends on react-hook-form bindings
 * (`control`, `handleSubmit`, etc.) without requiring a full form setup per test.
 *
 * @example
 * ```tsx
 * renderWithForm({ schema, defaultValues: { name: '' } }, ({ control }) => (
 *   <SynTextField name="name" control={control} label="Name" />
 * ))
 * ```
 */
export function renderWithForm<T extends FieldValues>(
  options: { schema: ZodType<T>; defaultValues: DefaultValues<T> },
  children: (form: UseFormReturn<T>) => ReactNode
) {
  return render(<RenderWithFormWrapper {...options}>{children}</RenderWithFormWrapper>)
}
