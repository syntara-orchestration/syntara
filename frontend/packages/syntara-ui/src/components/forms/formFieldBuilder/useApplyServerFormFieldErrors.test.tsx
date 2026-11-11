import type { FormDefinition, FormFieldType } from '@syntara/contracts'
import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { FormProvider, useForm, useFormState } from 'react-hook-form'
import { describe, expect, it } from 'vitest'

import { FormFieldTypeEnum } from '../../../forms'

import { createDefaultField } from './createDefaultField'
import type { FormDefinitionFieldServerError } from './formDefinitionFieldServerError'
import { dateFieldIncludeTimeErrorMessage } from './formFieldBuilderDateIncludeTimeError'
import { useApplyServerFormFieldErrors } from './useApplyServerFormFieldErrors'

function LabelErrorDisplay() {
  const { errors } = useFormState<FormDefinition>()
  const labelMessage = errors.fields?.[0]?.label?.message
  return <div data-testid="label-error">{typeof labelMessage === 'string' ? labelMessage : ''}</div>
}

function IncludeTimeErrorDisplay() {
  const { errors } = useFormState<FormDefinition>()
  return <div data-testid="include-time-error">{dateFieldIncludeTimeErrorMessage(errors, 0) ?? ''}</div>
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
            message: 'Select a time when both date and timezone are selected.',
          },
        ]}
      />
    )

    await waitFor(() => {
      expect(screen.getByTestId('include-time-error')).toHaveTextContent(
        'Select a time when both date and timezone are selected.'
      )
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
