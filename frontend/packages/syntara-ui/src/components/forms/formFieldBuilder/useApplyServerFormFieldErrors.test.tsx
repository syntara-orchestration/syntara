import type { FormDefinition } from '@syntara/contracts'
import { render, screen, waitFor } from '@testing-library/react'
import { FormProvider, useForm, useFormState } from 'react-hook-form'
import { describe, expect, it } from 'vitest'

import { FormFieldTypeEnum } from '../../../forms'

import { createDefaultField } from './createDefaultField'
import type { FormDefinitionFieldServerError } from './formDefinitionFieldServerError'
import { useApplyServerFormFieldErrors } from './useApplyServerFormFieldErrors'

function LabelErrorDisplay() {
  const { errors } = useFormState<FormDefinition>()
  const labelMessage = errors.fields?.[0]?.label?.message
  return <div data-testid="label-error">{typeof labelMessage === 'string' ? labelMessage : ''}</div>
}

function TestHarness({
  serverFieldErrors,
}: Readonly<{ serverFieldErrors?: ReadonlyArray<FormDefinitionFieldServerError> }>) {
  const field = createDefaultField(FormFieldTypeEnum.TEXT)
  const methods = useForm<FormDefinition>({ defaultValues: { fields: [field] } })
  useApplyServerFormFieldErrors(methods, serverFieldErrors)
  return (
    <FormProvider {...methods}>
      <LabelErrorDisplay />
    </FormProvider>
  )
}

describe('useApplyServerFormFieldErrors', () => {
  it('maps server errors onto form field paths', async () => {
    render(<TestHarness serverFieldErrors={[{ fieldIndex: 0, subPath: 'label', message: 'Label is required' }]} />)

    await waitFor(() => {
      expect(screen.getByTestId('label-error')).toHaveTextContent('Label is required')
    })
  })

  it('clears previously applied server errors when the list becomes empty', async () => {
    const { rerender } = render(
      <TestHarness serverFieldErrors={[{ fieldIndex: 0, subPath: 'label', message: 'Label is required' }]} />
    )

    await waitFor(() => {
      expect(screen.getByTestId('label-error')).toHaveTextContent('Label is required')
    })

    rerender(<TestHarness serverFieldErrors={[]} />)

    await waitFor(() => {
      expect(screen.getByTestId('label-error')).toHaveTextContent('')
    })
  })
})
