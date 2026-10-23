import { TriggerTypeEnum } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { VersionViewContext } from '../VersionViewContext'

import { FormTriggerConfigurationFields } from './FormTriggerConfigurationFields'
import type { TriggerFormData } from './triggerFormSchema'

vi.mock('../../../components/forms/SynFormFieldBuilder', () => ({
  SynFormFieldBuilder: () => <div data-testid="syn-form-field-builder" />,
}))

vi.mock('./FormPromptPreviewModal', () => ({
  FormPromptPreviewModal: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="form-preview-modal" /> : null,
}))

vi.mock('./FormPresentationOptionsSection', () => ({
  FormPresentationOptionsSection: () => <div data-testid="presentation-options" />,
}))

type RenderFieldsOptions = {
  formDefinitionError?: { message?: string }
}

function renderFields(options: RenderFieldsOptions = {}) {
  function Wrapper() {
    const methods = useForm<TriggerFormData>({
      defaultValues: {
        triggerType: TriggerTypeEnum.FORM_TRIGGER,
        form_definition: createEmptyFormDefinition(),
        message: '',
        submit_label: '',
        success_message: '',
        css_override: '',
      },
    })
    return (
      <VersionViewContext value={false}>
        <FormProvider {...methods}>
          <FormTriggerConfigurationFields formDefinitionError={options.formDefinitionError} />
        </FormProvider>
      </VersionViewContext>
    )
  }
  return render(<Wrapper />)
}

describe('FormTriggerConfigurationFields', () => {
  it('has no accessibility violations', async () => {
    const { container } = renderFields()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders form trigger guidance, field builder, and preview entry point', async () => {
    const user = userEvent.setup()
    renderFields()

    expect(screen.getByText('Form trigger')).toBeInTheDocument()
    expect(screen.getByTestId('syn-form-field-builder')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Preview form' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Preview form' }))
    expect(screen.getByTestId('form-preview-modal')).toBeInTheDocument()
  })

  it('shows form definition validation error from publish', () => {
    renderFields({ formDefinitionError: { message: 'Add at least one form field.' } })

    expect(screen.getByText('Add at least one form field.')).toBeInTheDocument()
  })
})
