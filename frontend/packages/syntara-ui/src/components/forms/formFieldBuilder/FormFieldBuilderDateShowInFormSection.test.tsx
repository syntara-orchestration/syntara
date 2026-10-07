import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { DATE_FIELD_TIME_REQUIRES_TIMEZONE_MESSAGE, FormFieldTypeEnum, parseFormDefinition } from '../../../forms'

import { FormFieldBuilderCommitContext } from './formFieldBuilderCommitContext'
import { FormFieldBuilderDateShowInFormSection } from './FormFieldBuilderDateShowInFormSection'

function renderSection(definition: ReturnType<typeof parseFormDefinition>, onCommit = vi.fn()) {
  function Wrapper() {
    const methods = useForm({ defaultValues: definition })
    return (
      <FormFieldBuilderCommitContext.Provider value={onCommit}>
        <FormProvider {...methods}>
          <FormFieldBuilderDateShowInFormSection index={0} idPrefix="field-0" />
        </FormProvider>
      </FormFieldBuilderCommitContext.Provider>
    )
  }
  return render(<Wrapper />)
}

describe('FormFieldBuilderDateShowInFormSection', () => {
  it('has no accessibility violations', async () => {
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' }],
    })
    const { container } = renderSection(definition)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders show-in-form checkboxes for date fields', () => {
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' }],
    })
    renderSection(definition)

    expect(screen.getByRole('checkbox', { name: 'Date' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Time' })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Timezone' })).not.toBeChecked()
  })

  it('shows how to fix time without timezone', async () => {
    const user = userEvent.setup()
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' }],
    })
    renderSection(definition)

    await user.click(screen.getByRole('checkbox', { name: 'Time' }))

    expect(screen.getByText(DATE_FIELD_TIME_REQUIRES_TIMEZONE_MESSAGE)).toBeInTheDocument()
  })

  it('enables time without selecting timezone', async () => {
    const user = userEvent.setup()
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' }],
    })
    renderSection(definition)

    await user.click(screen.getByRole('checkbox', { name: 'Time' }))

    expect(screen.getByRole('checkbox', { name: 'Time' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Timezone' })).not.toBeChecked()
  })

  it('disables the only selected show-in-form checkbox', () => {
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' }],
    })
    renderSection(definition)

    expect(screen.getByRole('checkbox', { name: 'Date' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Time' })).toBeEnabled()
    expect(screen.getByRole('checkbox', { name: 'Timezone' })).toBeEnabled()
  })

  it('unchecks timezone without unchecking time', async () => {
    const user = userEvent.setup()
    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DATE,
          value_name: 'due',
          label: 'Due',
          include_date: true,
          include_time: true,
          include_timezone: true,
        },
      ],
    })
    renderSection(definition)

    await user.click(screen.getByRole('checkbox', { name: 'Timezone' }))

    expect(screen.getByRole('checkbox', { name: 'Time' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Timezone' })).not.toBeChecked()
  })

  it('allows timezone only without time', async () => {
    const user = userEvent.setup()
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' }],
    })
    renderSection(definition)

    await user.click(screen.getByRole('checkbox', { name: 'Timezone' }))

    expect(screen.getByRole('checkbox', { name: 'Timezone' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Time' })).not.toBeChecked()
  })
})
