import type { FormDefinition } from '@syntara/contracts'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import {
  DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE,
  FormFieldTypeEnum,
  parseFormDefinition,
} from '../../../forms'

import { createDefaultField } from './createDefaultField'
import type { FormDefinitionFieldServerError } from './formDefinitionFieldServerError'
import { FormFieldBuilderCommitContext } from './formFieldBuilderCommitContext'
import { FormFieldBuilderDateShowInFormSection } from './FormFieldBuilderDateShowInFormSection'
import { FormFieldBuilderDraftModeContext } from './formFieldBuilderDraftModeContext'
import { useApplyServerFormFieldErrors } from './useApplyServerFormFieldErrors'

type RenderSectionOptions = Readonly<{
  draftMode?: boolean
  serverFieldErrors?: ReadonlyArray<FormDefinitionFieldServerError>
}>

function expectAccessibleCombinationError() {
  const showInFormGroup = screen.getByRole('group', { name: 'Show in form' })
  expect(showInFormGroup).toHaveAttribute('aria-labelledby', 'field-0-show-in-form-label')
  expect(showInFormGroup).toHaveAttribute('aria-describedby', 'field-0-show-in-form-error')
  expect(screen.getByText(DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE)).toBeVisible()
  expect(within(showInFormGroup).getByRole('checkbox', { name: 'Time' })).toHaveAttribute('aria-invalid', 'true')
}

function renderSection(definition: FormDefinition, options: RenderSectionOptions = {}, onCommit = vi.fn()) {
  const serverFieldErrors = options.serverFieldErrors

  function Wrapper() {
    const methods = useForm<FormDefinition>({ defaultValues: definition })
    useApplyServerFormFieldErrors(methods, serverFieldErrors)

    return (
      <FormFieldBuilderDraftModeContext.Provider value={options.draftMode ?? false}>
        <FormFieldBuilderCommitContext.Provider value={onCommit}>
          <FormProvider {...methods}>
            <FormFieldBuilderDateShowInFormSection index={0} idPrefix="field-0" />
          </FormProvider>
        </FormFieldBuilderCommitContext.Provider>
      </FormFieldBuilderDraftModeContext.Provider>
    )
  }
  return render(<Wrapper />)
}

const INCLUDE_TIME_SERVER_ERROR: FormDefinitionFieldServerError = {
  fieldIndex: 0,
  subPath: 'include_time',
  message: DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE,
}

/** Invalid date show-in-form combo (zod rejects this); used to assert server errors apply in draft. */
function dateFieldWithDateAndTimezoneNoTime(): FormDefinition {
  const field = createDefaultField(FormFieldTypeEnum.DATE)
  if (field.type !== FormFieldTypeEnum.DATE) {
    throw new Error('expected date field fixture')
  }
  return { fields: [{ ...field, include_timezone: true }] }
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

  it('does not show inline validation in draft mode when date and timezone are on without time', async () => {
    const user = userEvent.setup()
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' }],
    })
    renderSection(definition, { draftMode: true })

    await user.click(screen.getByRole('checkbox', { name: 'Timezone' }))

    expect(screen.queryByText(DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE)).not.toBeInTheDocument()
  })

  it('shows an accessible checkbox-group error in strict mode when date and timezone are on without time', async () => {
    const user = userEvent.setup()
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' }],
    })
    renderSection(definition, { draftMode: false })

    await user.click(screen.getByRole('checkbox', { name: 'Timezone' }))

    expectAccessibleCombinationError()
  })

  it('shows verify findings on the field in draft mode when include_time has a server error', async () => {
    renderSection(dateFieldWithDateAndTimezoneNoTime(), {
      draftMode: true,
      serverFieldErrors: [INCLUDE_TIME_SERVER_ERROR],
    })

    await waitFor(() => {
      expectAccessibleCombinationError()
    })
  })

  it('has no accessibility violations when the combination error is shown', async () => {
    const { container } = renderSection(dateFieldWithDateAndTimezoneNoTime(), {
      serverFieldErrors: [INCLUDE_TIME_SERVER_ERROR],
    })

    await waitFor(() => {
      expect(screen.getByText(DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE)).toBeVisible()
    })
    expect(await axe(container)).toHaveNoViolations()
  })

  it('allows time without timezone after date is unchecked', async () => {
    const user = userEvent.setup()
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due' }],
    })
    renderSection(definition)

    await user.click(screen.getByRole('checkbox', { name: 'Time' }))
    await user.click(screen.getByRole('checkbox', { name: 'Date' }))

    expect(screen.getByRole('checkbox', { name: 'Date' })).not.toBeChecked()
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
      fields: [
        {
          type: FormFieldTypeEnum.DATE,
          value_name: 'due',
          label: 'Due',
          include_date: false,
          include_timezone: true,
        },
      ],
    })
    renderSection(definition)

    await user.click(screen.getByRole('checkbox', { name: 'Timezone' }))

    expect(screen.getByRole('checkbox', { name: 'Timezone' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Time' })).not.toBeChecked()
  })
})
