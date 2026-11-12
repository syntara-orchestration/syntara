import { FormFieldDisplayEnum } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldTypeEnum } from '../../../forms'
import type { FormSubmissionInput } from '../../../forms'

import { SynDynamicFormField } from './SynDynamicFormField'

type CapturedSynTextAreaFieldProps = {
  className?: string
  label: string
}

const capturedTextAreaProps = vi.hoisted(() => ({ current: null as CapturedSynTextAreaFieldProps | null }))

vi.mock('../SynTextAreaField', () => ({
  SynTextAreaField: (props: CapturedSynTextAreaFieldProps) => {
    capturedTextAreaProps.current = props
    return <textarea aria-label={props.label} readOnly />
  },
}))

function TextAreaFieldHarness({ textAreaControlClassName }: { textAreaControlClassName?: string }) {
  const form = useForm<FormSubmissionInput>({ defaultValues: { notes: '' } })
  return (
    <FormProvider {...form}>
      <SynDynamicFormField
        field={{
          value_name: 'notes',
          type: FormFieldTypeEnum.TEXT,
          display: FormFieldDisplayEnum.MULTI_LINE,
          label: 'Notes',
          required: false,
        }}
        textAreaControlClassName={textAreaControlClassName}
      />
    </FormProvider>
  )
}

function MaskedTextFieldHarness() {
  const form = useForm<FormSubmissionInput>({ defaultValues: { token: '' } })
  return (
    <FormProvider {...form}>
      <SynDynamicFormField
        field={{
          value_name: 'token',
          type: FormFieldTypeEnum.TEXT,
          display: FormFieldDisplayEnum.MASKED,
          label: 'Token',
        }}
      />
    </FormProvider>
  )
}

describe('SynDynamicFormField', () => {
  it('forwards textAreaControlClassName to textarea fields', () => {
    capturedTextAreaProps.current = null
    render(<TextAreaFieldHarness textAreaControlClassName="form-step-textarea-bounds" />)

    expect(screen.getByRole('textbox', { name: 'Notes' })).toBeInTheDocument()
    expect(capturedTextAreaProps.current).toEqual(
      expect.objectContaining({ className: 'form-step-textarea-bounds', label: 'Notes' })
    )
  })

  it('renders masked text as a password input', () => {
    render(<MaskedTextFieldHarness />)

    expect(screen.getByLabelText('Token')).toHaveAttribute('type', 'password')
  })

  it('has no accessibility violations for a masked text field', async () => {
    const { container } = render(<MaskedTextFieldHarness />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
