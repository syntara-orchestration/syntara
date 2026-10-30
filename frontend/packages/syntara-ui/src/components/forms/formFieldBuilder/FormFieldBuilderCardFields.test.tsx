import type { FormField } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'

import type { FormDefinitionSchemaInput } from '../../../forms'
import { FormFieldTypeEnum } from '../../../forms'

import { createDefaultField } from './createDefaultField'
import { FormFieldBuilderCardFields } from './FormFieldBuilderCardFields'
import { FormFieldBuilderCommitContext } from './formFieldBuilderCommitContext'

type CapturedSynTextFieldProps = {
  label: string
  name: string
}

const synTextAreaFieldRender = vi.hoisted(() => vi.fn())
const capturedHelpTextField = vi.hoisted(() => ({ current: null as CapturedSynTextFieldProps | null }))

vi.mock('../SynTextAreaField', () => ({
  SynTextAreaField: () => {
    synTextAreaFieldRender()
    return null
  },
}))

vi.mock('../SynTextField', () => ({
  SynTextField: (props: CapturedSynTextFieldProps) => {
    if (props.name.endsWith('.help_text')) {
      capturedHelpTextField.current = props
    }
    return <input aria-label={props.label} readOnly />
  },
}))

vi.mock('./FormFieldBuilderFieldTypeSelect', () => ({
  FormFieldBuilderFieldTypeSelect: () => null,
}))

vi.mock('./FormFieldBuilderFieldDefaultEditor', () => ({
  FormFieldBuilderFieldDefaultEditor: () => null,
}))

function renderHelpTextForFieldType(field: FormField) {
  capturedHelpTextField.current = null
  synTextAreaFieldRender.mockClear()

  function Harness() {
    const form = useForm<FormDefinitionSchemaInput>({
      defaultValues: { fields: [field] },
    })

    return (
      <FormFieldBuilderCommitContext.Provider value={vi.fn()}>
        <FormProvider {...form}>
          <FormFieldBuilderCardFields
            index={0}
            field={field}
            idPrefix="field-0"
            valueNameLooksGenerated={false}
            onTypeChange={vi.fn()}
          />
        </FormProvider>
      </FormFieldBuilderCommitContext.Provider>
    )
  }

  render(<Harness />)
}

describe('FormFieldBuilderCardFields', () => {
  it.each([FormFieldTypeEnum.CHECKBOX, FormFieldTypeEnum.DATE, FormFieldTypeEnum.TEXT])(
    'renders help text as a single-line text input for %s fields',
    (fieldType) => {
      renderHelpTextForFieldType(createDefaultField(fieldType))

      expect(screen.getByRole('textbox', { name: 'Help text' })).toBeInTheDocument()
      expect(capturedHelpTextField.current).toEqual(
        expect.objectContaining({ label: 'Help text', name: 'fields.0.help_text' })
      )
      expect(synTextAreaFieldRender).not.toHaveBeenCalled()
    }
  )
})
