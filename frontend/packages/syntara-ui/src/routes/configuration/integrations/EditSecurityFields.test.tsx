import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLayoutEffect } from 'react'
import { useForm, type UseFormReturn } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynForm } from '../../../components/forms/SynForm'

import type { EditIntegrationFormValues } from './editIntegrationFormSchema'
import { EditSecurityFields } from './EditSecurityFields'

function TestWrapper({
  defaultValues,
  formRef,
}: Readonly<{
  defaultValues?: Partial<EditIntegrationFormValues>
  formRef?: { current: UseFormReturn<EditIntegrationFormValues> | undefined }
}>) {
  const form = useForm<EditIntegrationFormValues>({
    defaultValues: {
      name: 'test',
      description: '',
      integration_type: 'mcp_server',
      allow_http: false,
      insecure_skip_tls_verify: false,
      ca_certificate: null,
      scope: 'global',
      project_ids: [],
      management_credential_id: null,
      ...defaultValues,
    },
  })

  useLayoutEffect(() => {
    if (formRef) {
      formRef.current = form
    }
  }, [form, formRef])

  return (
    <SynForm form={form}>
      <EditSecurityFields />
    </SynForm>
  )
}

describe('EditSecurityFields', () => {
  it('starts collapsed and expands on toggle', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    expect(screen.queryByRole('checkbox', { name: /allow http connections/i })).not.toBeInTheDocument()

    await user.click(screen.getByText('Security'))

    expect(screen.getByRole('checkbox', { name: /allow http connections/i })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /disable tls certificate verification/i })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /ca certificate/i })).toBeInTheDocument()
  })

  it('collapses when toggled again', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByText('Security'))
    expect(screen.getByRole('checkbox', { name: /allow http connections/i })).toBeInTheDocument()

    await user.click(screen.getByText('Security'))
    expect(screen.queryByRole('checkbox', { name: /allow http connections/i })).not.toBeInTheDocument()
  })

  it('toggles Allow HTTP checkbox', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByText('Security'))
    const checkbox = screen.getByRole('checkbox', { name: /allow http connections/i })
    expect(checkbox).not.toBeChecked()

    await user.click(checkbox)
    expect(checkbox).toBeChecked()

    await user.click(checkbox)
    expect(checkbox).not.toBeChecked()
  })

  it('toggles Disable TLS certificate verification checkbox', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByText('Security'))
    const checkbox = screen.getByRole('checkbox', { name: /disable tls certificate verification/i })
    expect(checkbox).not.toBeChecked()

    await user.click(checkbox)
    expect(checkbox).toBeChecked()

    await user.click(checkbox)
    expect(checkbox).not.toBeChecked()
  })

  it('accepts CA certificate input', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByText('Security'))
    const textarea = screen.getByRole('textbox', { name: /ca certificate/i })
    expect(textarea).toHaveValue('')

    await user.type(textarea, 'cert-data')
    expect(textarea).toHaveValue('cert-data')
  })

  it('sets ca_certificate to null when textarea is cleared', async () => {
    const user = userEvent.setup()
    const formRef: { current: UseFormReturn<EditIntegrationFormValues> | undefined } = { current: undefined }
    render(<TestWrapper defaultValues={{ ca_certificate: 'existing-cert' }} formRef={formRef} />)

    await user.click(screen.getByText('Security'))
    const textarea = screen.getByRole('textbox', { name: /ca certificate/i })
    expect(textarea).toHaveValue('existing-cert')

    await user.clear(textarea)
    expect(textarea).toHaveValue('')
    expect(formRef.current!.getValues('ca_certificate')).toBeNull()
  })

  it('renders null ca_certificate as empty string in textarea', async () => {
    const user = userEvent.setup()
    render(<TestWrapper defaultValues={{ ca_certificate: null }} />)

    await user.click(screen.getByText('Security'))

    const textarea = screen.getByRole('textbox', { name: /ca certificate/i })
    expect(textarea).toHaveValue('')
  })

  it('renders existing ca_certificate value in textarea', async () => {
    const user = userEvent.setup()
    render(<TestWrapper defaultValues={{ ca_certificate: 'my-cert-value' }} />)

    await user.click(screen.getByText('Security'))

    const textarea = screen.getByRole('textbox', { name: /ca certificate/i })
    expect(textarea).toHaveValue('my-cert-value')
  })

  it('reflects pre-set checkbox values', async () => {
    const user = userEvent.setup()
    render(<TestWrapper defaultValues={{ allow_http: true, insecure_skip_tls_verify: true }} />)

    await user.click(screen.getByText('Security'))

    expect(screen.getByRole('checkbox', { name: /allow http connections/i })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /disable tls certificate verification/i })).toBeChecked()
  })

  it('renders helper text for CA certificate', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByText('Security'))

    expect(screen.getByText(/PEM-encoded CA certificate/)).toBeInTheDocument()
  })

  it('hides CA certificate field when TLS verification is disabled', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByText('Security'))
    expect(screen.getByRole('textbox', { name: /ca certificate/i })).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: /disable tls certificate verification/i }))
    expect(screen.queryByRole('textbox', { name: /ca certificate/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/PEM-encoded CA certificate/)).not.toBeInTheDocument()
  })

  it('shows warning when TLS verification is disabled', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByText('Security'))
    expect(screen.queryByText(/will not be verified/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: /disable tls certificate verification/i }))
    expect(screen.getByText(/will not be verified. Only enable in trusted networks/)).toBeInTheDocument()
  })

  it('restores CA certificate field when TLS verification is re-enabled', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByText('Security'))
    await user.click(screen.getByRole('checkbox', { name: /disable tls certificate verification/i }))
    expect(screen.queryByRole('textbox', { name: /ca certificate/i })).not.toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: /disable tls certificate verification/i }))
    expect(screen.getByRole('textbox', { name: /ca certificate/i })).toBeInTheDocument()
    expect(screen.queryByText(/will not be verified/)).not.toBeInTheDocument()
  })

  it('hides CA certificate field when insecure_skip_tls_verify defaults to true', async () => {
    const user = userEvent.setup()
    render(<TestWrapper defaultValues={{ insecure_skip_tls_verify: true }} />)

    await user.click(screen.getByText('Security'))
    expect(screen.queryByRole('textbox', { name: /ca certificate/i })).not.toBeInTheDocument()
    expect(screen.getByText(/will not be verified/)).toBeInTheDocument()
  })

  it('auto-expands when ca_certificate has a validation error', async () => {
    const formRef: { current: UseFormReturn<EditIntegrationFormValues> | undefined } = { current: undefined }
    render(<TestWrapper formRef={formRef} />)

    expect(screen.queryByRole('textbox', { name: /ca certificate/i })).not.toBeInTheDocument()

    act(() => {
      formRef.current!.setError('ca_certificate', { type: 'server', message: 'Invalid PEM format' })
    })

    await screen.findByRole('textbox', { name: /ca certificate/i })
    expect(screen.getByText('Invalid PEM format')).toBeInTheDocument()
  })

  it('stays expanded while ca_certificate error is present', async () => {
    const user = userEvent.setup()
    const formRef: { current: UseFormReturn<EditIntegrationFormValues> | undefined } = { current: undefined }
    render(<TestWrapper formRef={formRef} />)

    act(() => {
      formRef.current!.setError('ca_certificate', { type: 'server', message: 'Invalid PEM format' })
    })

    await screen.findByRole('textbox', { name: /ca certificate/i })

    await user.click(screen.getByText('Security'))

    expect(screen.getByRole('textbox', { name: /ca certificate/i })).toBeInTheDocument()
  })

  it('collapses automatically when ca_certificate error is cleared', async () => {
    const formRef: { current: UseFormReturn<EditIntegrationFormValues> | undefined } = { current: undefined }
    render(<TestWrapper formRef={formRef} />)

    act(() => {
      formRef.current!.setError('ca_certificate', { type: 'server', message: 'Invalid PEM format' })
    })

    await screen.findByRole('textbox', { name: /ca certificate/i })

    act(() => {
      formRef.current!.clearErrors('ca_certificate')
    })

    await waitFor(() => {
      expect(screen.queryByRole('textbox', { name: /ca certificate/i })).not.toBeInTheDocument()
    })
    expect(screen.queryByText('Invalid PEM format')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const user = userEvent.setup()
    const { container } = render(<TestWrapper />)

    await user.click(screen.getByText('Security'))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when TLS verification is disabled', async () => {
    const user = userEvent.setup()
    const { container } = render(<TestWrapper />)

    await user.click(screen.getByText('Security'))
    await user.click(screen.getByRole('checkbox', { name: /disable tls certificate verification/i }))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
