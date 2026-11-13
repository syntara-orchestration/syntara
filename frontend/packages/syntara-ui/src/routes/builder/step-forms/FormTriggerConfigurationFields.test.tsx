import { TriggerTypeEnum } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRef } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { FORM_PREVIEW_INCOMPLETE_TOOLTIP, FormFieldTypeEnum } from '../../../forms'
import { VersionViewContext } from '../VersionViewContext'

import { FormTriggerConfigurationFields } from './FormTriggerConfigurationFields'
import { TriggerFormFieldBuilderCommitRefContext } from './triggerFormFieldBuilderCommitContext'
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

const validPreviewFormDefinition = {
  fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name' }],
}

const incompletePreviewFormDefinition = {
  fields: [{ type: FormFieldTypeEnum.TEXT, value_name: '', label: '' }],
}

function renderFields(formDefinition = createEmptyFormDefinition()) {
  function Wrapper() {
    const builderCommitRef = useRef(null)
    const methods = useForm<TriggerFormData>({
      defaultValues: {
        triggerType: TriggerTypeEnum.FORM_TRIGGER,
        form_definition: formDefinition,
        message: '',
        submit_label: '',
        success_message: '',
      },
    })
    return (
      <VersionViewContext value={false}>
        <TriggerFormFieldBuilderCommitRefContext.Provider value={builderCommitRef}>
          <FormProvider {...methods}>
            <FormTriggerConfigurationFields />
          </FormProvider>
        </TriggerFormFieldBuilderCommitRefContext.Provider>
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
    renderFields(validPreviewFormDefinition)

    expect(screen.getByText('Form trigger')).toBeInTheDocument()
    expect(screen.getByTestId('syn-form-field-builder')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Preview form' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Preview form' }))
    expect(screen.getByTestId('form-preview-modal')).toBeInTheDocument()
  })

  it('keeps preview control focusable with tooltip when the form definition is incomplete', async () => {
    const user = userEvent.setup()
    renderFields(incompletePreviewFormDefinition)

    const previewButton = screen.getByRole('button', { name: 'Preview form' })
    expect(previewButton).toHaveAttribute('aria-disabled', 'true')
    expect(previewButton).not.toBeDisabled()

    await user.hover(previewButton)
    expect(await screen.findByText(FORM_PREVIEW_INCOMPLETE_TOOLTIP)).toBeInTheDocument()

    await user.click(previewButton)
    expect(screen.queryByTestId('form-preview-modal')).not.toBeInTheDocument()
  })
})
