import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldTypeEnum, type FormDefinition } from '../../../forms'

import { createDefaultField } from './createDefaultField'
import { FormFieldBuilderCommitContext } from './formFieldBuilderCommitContext'
import { FormFieldBuilderOptionsModeProvider } from './FormFieldBuilderOptionsModeProvider'
import { FormFieldBuilderOptionsSection, type AuthoredOptionsFormField } from './FormFieldBuilderOptionsSection'

function renderSection(optionsMode: 'default' | 'static-only', field: AuthoredOptionsFormField, onCommit = vi.fn()) {
  function Wrapper() {
    const methods = useForm<FormDefinition>({
      defaultValues: { fields: [field] },
    })
    return (
      <FormFieldBuilderOptionsModeProvider mode={optionsMode}>
        <FormFieldBuilderCommitContext.Provider value={onCommit}>
          <FormProvider {...methods}>
            <FormFieldBuilderOptionsSection index={0} field={field} idPrefix="field-0" />
          </FormProvider>
        </FormFieldBuilderCommitContext.Provider>
      </FormFieldBuilderOptionsModeProvider>
    )
  }
  return render(<Wrapper />)
}

describe('FormFieldBuilderOptionsSection', () => {
  it('has no accessibility violations in static-only mode', async () => {
    const field = createDefaultField(FormFieldTypeEnum.DROPDOWN) as AuthoredOptionsFormField
    const { container } = renderSection('static-only', field)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows static-only options source help in form trigger mode', async () => {
    const user = userEvent.setup()
    const field = createDefaultField(FormFieldTypeEnum.DROPDOWN) as AuthoredOptionsFormField
    renderSection('static-only', field)

    await user.click(screen.getByRole('button', { name: 'More info for Options source' }))
    expect(screen.getByText('Define a fixed list of options.')).toBeInTheDocument()
  })

  it('hides options source toggle in static-only mode and shows static editor', () => {
    const field = createDefaultField(FormFieldTypeEnum.DROPDOWN) as AuthoredOptionsFormField
    renderSection('static-only', field)

    expect(screen.queryByRole('button', { name: 'Dynamic' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Static' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add option' })).toBeInTheDocument()
  })

  it('shows static and dynamic toggles in default mode', () => {
    const field = createDefaultField(FormFieldTypeEnum.DROPDOWN) as AuthoredOptionsFormField
    renderSection('default', field)

    expect(screen.getByRole('button', { name: 'Static' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dynamic' })).toBeInTheDocument()
  })
})
