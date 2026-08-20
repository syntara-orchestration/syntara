import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { VersionViewProvider } from '../VersionViewContext'

import { approvalFormSchema, type ApprovalFormData } from './approvalFormSchema'
import { FallbackDecisionField } from './FallbackDecisionField'
import { zodResolver } from './shared/formSchemaUtils'
import {
  APPROVAL_FALLBACK_DISABLED_EXPLICIT_STOP,
  APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT,
  APPROVAL_FALLBACK_ENABLE_LINK,
  APPROVAL_FALLBACK_ENABLED_HELPER,
} from './shared/nodeFieldHelpText'

const { mockUseWorkflowEngineDefaults } = vi.hoisted(() => ({
  mockUseWorkflowEngineDefaults: vi.fn(),
}))

vi.mock('../hooks/useWorkflowEngineDefaults', () => ({
  useWorkflowEngineDefaults: mockUseWorkflowEngineDefaults,
}))

function mockEngineDefaults(continueOnFailure: boolean | null) {
  mockUseWorkflowEngineDefaults.mockReturnValue({
    defaults: { continueOnFailure, timeoutSeconds: { approval: 86400 } },
    isLoading: false,
  })
}

function FormWrapper({
  children,
  continueOnFailure,
  isVersionView = false,
}: Readonly<{
  children: ReactNode
  continueOnFailure?: boolean
  isVersionView?: boolean
}>) {
  const methods = useForm<ApprovalFormData>({
    resolver: zodResolver(approvalFormSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      name: 'Approval',
      settings: { continue_on_failure: continueOnFailure },
    },
  })
  return (
    <VersionViewProvider value={isVersionView}>
      <FormProvider {...methods}>{children}</FormProvider>
    </VersionViewProvider>
  )
}

function renderField(options?: {
  continueOnFailure?: boolean
  adminDefault?: boolean | null
  isVersionView?: boolean
}) {
  mockEngineDefaults(options?.adminDefault ?? false)
  return render(<FallbackDecisionField />, {
    wrapper: ({ children }) => (
      <FormWrapper continueOnFailure={options?.continueOnFailure} isVersionView={options?.isVersionView}>
        {children}
      </FormWrapper>
    ),
  })
}

const fallbackToggle = () => screen.getByRole('button', { name: 'Fallback decision' })

describe('FallbackDecisionField', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('disables fallback decision when system default is stop on failure', () => {
    renderField({ adminDefault: false })

    expect(fallbackToggle()).toBeDisabled()
    expect(screen.getByText(APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT, { exact: false })).toHaveTextContent(
      APPROVAL_FALLBACK_ENABLE_LINK
    )
    expect(screen.getByRole('button', { name: APPROVAL_FALLBACK_ENABLE_LINK })).toBeInTheDocument()
  })

  it('disables fallback decision when the node is set to stop the workflow', () => {
    renderField({ continueOnFailure: false, adminDefault: true })

    expect(fallbackToggle()).toBeDisabled()
    expect(screen.getByText(APPROVAL_FALLBACK_DISABLED_EXPLICIT_STOP, { exact: false })).toHaveTextContent(
      APPROVAL_FALLBACK_ENABLE_LINK
    )
    expect(screen.getByRole('button', { name: APPROVAL_FALLBACK_ENABLE_LINK })).toBeInTheDocument()
  })

  it('enables fallback decision when the node continue on failure is true', () => {
    renderField({ continueOnFailure: true, adminDefault: false })

    expect(fallbackToggle()).toBeEnabled()
    expect(screen.getByText(APPROVAL_FALLBACK_ENABLED_HELPER)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: APPROVAL_FALLBACK_ENABLE_LINK })).not.toBeInTheDocument()
  })

  it('enables fallback decision when system default is continue on failure', () => {
    renderField({ adminDefault: true })

    expect(fallbackToggle()).toBeEnabled()
    expect(screen.getByText(APPROVAL_FALLBACK_ENABLED_HELPER)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: APPROVAL_FALLBACK_ENABLE_LINK })).not.toBeInTheDocument()
  })

  it('enables fallback when the system default later becomes continue on failure', () => {
    const { rerender } = renderField({ adminDefault: false })

    expect(fallbackToggle()).toBeDisabled()

    mockEngineDefaults(true)
    rerender(<FallbackDecisionField />)

    expect(fallbackToggle()).toBeEnabled()
    expect(screen.getByText(APPROVAL_FALLBACK_ENABLED_HELPER)).toBeInTheDocument()
  })

  it('shows a tooltip with the warning copy on the disabled dropdown', async () => {
    const user = userEvent.setup()
    renderField({ adminDefault: false })

    await user.hover(screen.getByRole('group', { name: 'Fallback decision is disabled' }))

    expect(await screen.findByRole('tooltip')).toHaveTextContent(APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT)
  })

  it('enables the dropdown and clears the warning when Enable continue on failure is clicked', async () => {
    const user = userEvent.setup()
    renderField({ adminDefault: false })

    await user.click(screen.getByRole('button', { name: APPROVAL_FALLBACK_ENABLE_LINK }))

    expect(fallbackToggle()).toBeEnabled()
    expect(screen.getByText(APPROVAL_FALLBACK_ENABLED_HELPER)).toBeInTheDocument()
    expect(screen.queryByText(APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: APPROVAL_FALLBACK_ENABLE_LINK })).not.toBeInTheDocument()
  })

  it('lets the user change fallback decision after enabling continue on failure', async () => {
    const user = userEvent.setup()
    renderField({ adminDefault: false })

    await user.click(screen.getByRole('button', { name: APPROVAL_FALLBACK_ENABLE_LINK }))
    await user.click(fallbackToggle())
    await user.click(screen.getByRole('option', { name: 'Approve' }))

    expect(fallbackToggle()).toHaveTextContent('Approve')

    await user.click(fallbackToggle())
    await user.click(screen.getByRole('option', { name: 'Reject (default)' }))

    expect(fallbackToggle()).toHaveTextContent('Reject (default)')
  })

  it('does not open the dropdown while continue on failure is effectively off', async () => {
    const user = userEvent.setup()
    renderField({ adminDefault: false })

    await user.click(screen.getByRole('group', { name: 'Fallback decision is disabled' }))

    expect(fallbackToggle()).toBeDisabled()
    expect(screen.queryByRole('option', { name: 'Approve' })).not.toBeInTheDocument()
  })

  it('hides the enable link and tooltip in version view', async () => {
    const user = userEvent.setup()
    renderField({ adminDefault: false, isVersionView: true })

    expect(fallbackToggle()).toBeDisabled()
    expect(screen.getByText(APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: APPROVAL_FALLBACK_ENABLE_LINK })).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Fallback decision is disabled' })).not.toBeInTheDocument()

    await user.hover(fallbackToggle())
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('keeps fallback decision disabled in version view when continue on failure is on', () => {
    renderField({ continueOnFailure: true, isVersionView: true })

    expect(fallbackToggle()).toBeDisabled()
    expect(screen.getByText(APPROVAL_FALLBACK_ENABLED_HELPER)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: APPROVAL_FALLBACK_ENABLE_LINK })).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Fallback decision is disabled' })).not.toBeInTheDocument()
  })

  it('mentions Continue on failure in the field help popover', async () => {
    const user = userEvent.setup()
    renderField({ continueOnFailure: true })

    await user.click(screen.getByRole('button', { name: 'More info for Fallback decision' }))

    expect(await screen.findByText(/Requires Continue on failure to be enabled/i)).toBeInTheDocument()
  })

  it('has no accessibility violations when disabled', async () => {
    const { container } = renderField({ adminDefault: false })
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations when enabled', async () => {
    const { container } = renderField({ continueOnFailure: true })
    expect(await axe(container)).toHaveNoViolations()
  })
})
