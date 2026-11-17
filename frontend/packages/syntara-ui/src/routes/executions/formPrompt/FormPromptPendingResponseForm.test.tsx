import type { FormsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { FormFieldTypeEnum } from '../../../forms'

import { FormPromptPendingResponseForm } from './FormPromptPendingResponseForm'

type FormDefinition = FormsAPI.components['schemas']['FormDefinition']

vi.mock('../../../components/forms/SynDynamicForm', () => ({
  SynDynamicForm: ({ definition }: { definition?: { fields?: Array<{ value_name: string; label: string }> } }) => (
    <form aria-label="Form prompt fields">
      {definition?.fields?.map((field) => (
        <label key={field.value_name} htmlFor={field.value_name}>
          {field.label}
        </label>
      ))}
    </form>
  ),
}))

const definition: FormDefinition = {
  fields: [
    {
      value_name: 'summary',
      type: FormFieldTypeEnum.TEXT,
      label: 'Summary',
      required: true,
    },
  ],
}

const baseProps = {
  responseFormId: 'form-prompt-response-fp-1',
  definition,
  submitLabel: 'Send',
  isDisabled: false,
  isReadOnly: false,
  onSubmit: vi.fn(),
}

describe('FormPromptPendingResponseForm', () => {
  it('renders the dynamic form fields', () => {
    render(<FormPromptPendingResponseForm {...baseProps} />)

    expect(screen.getByRole('form', { name: 'Form prompt fields' })).toBeInTheDocument()
    expect(screen.getByText('Summary')).toBeInTheDocument()
  })
})
