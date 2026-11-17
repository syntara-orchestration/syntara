import type { FormDefinition, FormFieldType } from '@syntara/contracts'
import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { FormProvider, useController, useForm, useFormContext, useFormState } from 'react-hook-form'
import { describe, expect, it } from 'vitest'

import { DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE, FormFieldTypeEnum } from '../../../forms'

import { createDefaultField } from './createDefaultField'
import type { FormDefinitionFieldServerError } from './formDefinitionFieldServerError'
import { useApplyServerFormFieldErrors } from './useApplyServerFormFieldErrors'

function LabelErrorDisplay() {
  const { errors } = useFormState<FormDefinition>()
  const labelMessage = errors.fields?.[0]?.label?.message
  return <div data-testid="label-error">{typeof labelMessage === 'string' ? labelMessage : ''}</div>
}

function IncludeTimeErrorDisplay() {
  const { control } = useFormContext<FormDefinition>()
  const { fieldState } = useController({ control, name: 'fields.0.include_time' })
  const message = fieldState.error?.message
  if (typeof message !== 'string' || message.length === 0) {
    return null
  }
  return <p>{message}</p>
}

function TestHarness({
  serverFieldErrors,
  fieldType = FormFieldTypeEnum.TEXT,
  errorDisplay = <LabelErrorDisplay />,
}: Readonly<{
  serverFieldErrors?: ReadonlyArray<FormDefinitionFieldServerError>
  fieldType?: FormFieldType
  errorDisplay?: ReactNode
}>) {
  const field = createDefaultField(fieldType)
  const methods = useForm<FormDefinition>({ defaultValues: { fields: [field] } })
  useApplyServerFormFieldErrors(methods, serverFieldErrors)
  return <FormProvider {...methods}>{errorDisplay}</FormProvider>
}

describe('useApplyServerFormFieldErrors', () => {
  it('maps server errors onto form field paths', async () => {
    render(<TestHarness serverFieldErrors={[{ fieldIndex: 0, subPath: 'label', message: 'Label is required' }]} />)

    await waitFor(() => {
      expect(screen.getByTestId('label-error')).toHaveTextContent('Label is required')
    })
  })

  it('maps include_time server errors onto form field paths', async () => {
    render(
      <TestHarness
        fieldType={FormFieldTypeEnum.DATE}
        errorDisplay={<IncludeTimeErrorDisplay />}
        serverFieldErrors={[
          {
            fieldIndex: 0,
            subPath: 'include_time',
            message: DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE,
          },
        ]}
      />
    )

    await waitFor(() => {
      expect(screen.getByText(DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE)).toBeVisible()
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
