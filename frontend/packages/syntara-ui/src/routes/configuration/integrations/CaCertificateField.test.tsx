import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLayoutEffect } from 'react'
import { useForm, type UseFormReturn } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynForm } from '../../../components/forms/SynForm'

import { CaCertificateField } from './CaCertificateField'

type FormValues = {
  ca_certificate: string | null
}

function TestWrapper({
  isRequired = false,
  defaultValue = null,
  formRef,
}: Readonly<{
  isRequired?: boolean
  defaultValue?: string | null
  formRef?: { current: UseFormReturn<FormValues> | undefined }
}>) {
  const form = useForm<FormValues>({ defaultValues: { ca_certificate: defaultValue } })

  useLayoutEffect(() => {
    if (formRef) {
      formRef.current = form
    }
  }, [form, formRef])

  return (
    <SynForm form={form}>
      <CaCertificateField<FormValues, 'ca_certificate'>
        name="ca_certificate"
        fieldId="ca-certificate"
        isRequired={isRequired}
      />
    </SynForm>
  )
}

describe('CaCertificateField', () => {
  it('marks the certificate required and shows the PEM hint', () => {
    render(<TestWrapper isRequired />)

    const certificate = screen.getByRole('textbox', { name: 'CA certificate' })
    // Assert the native HTML required attribute (PatternFly TextArea's isRequired),
    // not only aria-required — jest-dom's toBeRequired() also matches aria-required.
    expect(certificate).toHaveProperty('required', true)
    expect(certificate).toHaveAttribute('aria-required', 'true')
    expect(screen.getByText('*')).toBeInTheDocument()
    expect(screen.getByText(/PEM-encoded CA certificate/)).toBeInTheDocument()
  })

  it('leaves the certificate optional when it is not required', () => {
    render(<TestWrapper />)

    const certificate = screen.getByRole('textbox', { name: 'CA certificate' })
    expect(certificate).toHaveProperty('required', false)
    expect(certificate).not.toHaveAttribute('aria-required')
  })

  it('stores null when the textarea is cleared', async () => {
    const user = userEvent.setup()
    const formRef: { current: UseFormReturn<FormValues> | undefined } = { current: undefined }
    render(<TestWrapper defaultValue="existing-cert" formRef={formRef} />)

    const certificate = screen.getByRole('textbox', { name: 'CA certificate' })
    expect(certificate).toHaveValue('existing-cert')

    await user.clear(certificate)

    expect(certificate).toHaveValue('')
    expect(formRef.current?.getValues('ca_certificate')).toBeNull()
  })

  it('has no accessibility violations when required', async () => {
    const { container } = render(<TestWrapper isRequired />)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations when optional', async () => {
    const { container } = render(<TestWrapper />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
