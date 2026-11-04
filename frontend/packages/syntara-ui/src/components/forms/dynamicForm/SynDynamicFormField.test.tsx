import { render, screen } from '@testing-library/react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'

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
          type: FormFieldTypeEnum.TEXTAREA,
          label: 'Notes',
          required: false,
        }}
        textAreaControlClassName={textAreaControlClassName}
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
})
