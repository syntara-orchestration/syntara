import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { useWorkflowEngineDefaults } from '../hooks/useWorkflowEngineDefaults'
import { VersionViewContext } from '../VersionViewContext'

import type { NodeSettingsFormData } from './shared/nodeSettingsSchema'
import { SubWorkflowSettingsForm } from './SubWorkflowSettingsForm'

vi.mock('../hooks/useWorkflowEngineDefaults', () => ({
  useWorkflowEngineDefaults: vi.fn(),
}))

type SettingsFormData = { settings: NodeSettingsFormData }

type FormWrapperProps = {
  children: ReactNode
  settings?: NodeSettingsFormData
  isVersionView?: boolean
}

function FormWrapper({ children, settings = {}, isVersionView = false }: FormWrapperProps) {
  const methods = useForm<SettingsFormData>({ defaultValues: { settings } })

  return (
    <VersionViewContext.Provider value={isVersionView}>
      <FormProvider {...methods}>
        <form onSubmit={methods.handleSubmit(() => undefined)}>{children}</form>
      </FormProvider>
    </VersionViewContext.Provider>
  )
}

function renderSettingsForm(settings?: NodeSettingsFormData, isVersionView = false) {
  return render(
    <FormWrapper settings={settings} isVersionView={isVersionView}>
      <SubWorkflowSettingsForm />
    </FormWrapper>
  )
}

function setEngineDefault(continueOnFailure: boolean | null) {
  vi.mocked(useWorkflowEngineDefaults).mockReturnValue({
    defaults: {
      continueOnFailure,
      timeoutSeconds: { script: null, agentic: null, aap: null, approval: null, http_request: null },
      convergeWaitDuration: null,
      retry: { maxRetries: null, initialInterval: null, maxInterval: null, backoffCoefficient: null },
      maxLoopIterations: null,
    },
    isLoading: false,
  })
}

const failureToggle = () => screen.getByRole('button', { name: 'On failure behavior' })

describe('SubWorkflowSettingsForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useWorkflowEngineDefaults).mockReturnValue({ defaults: null, isLoading: false })
  })

  it('shows system defaults when the node has no overrides', () => {
    renderSettingsForm()

    expect(failureToggle()).toHaveTextContent('System default')
    expect(screen.getByRole('spinbutton', { name: 'Timeout (seconds)' })).toHaveAttribute(
      'placeholder',
      'System default'
    )
  })

  it.each([
    [undefined, 'System default'],
    [true, 'Continue on failure'],
    [false, 'Stop workflow or branch on failure'],
  ] as const)('shows the selected failure behavior for %s', (continueOnFailure, label) => {
    renderSettingsForm({ continue_on_failure: continueOnFailure })

    expect(failureToggle()).toHaveTextContent(label)
  })

  it.each([
    ['Continue on failure', 'Continue on failure'],
    ['Stop workflow or branch on failure', 'Stop workflow or branch on failure'],
    ['System default', 'System default'],
  ])('updates the override when selecting %s', async (option, expectedLabel) => {
    const user = userEvent.setup()
    renderSettingsForm({ continue_on_failure: true })

    await user.click(failureToggle())
    await user.click(await screen.findByRole('option', { name: new RegExp(`^${option}`) }))

    expect(failureToggle()).toHaveTextContent(expectedLabel)
  })

  it.each([
    [true, 'system default: continue on failure'],
    [false, 'system default: stop on failure'],
  ])('explains the configured system default (%s)', async (continueOnFailure, explanation) => {
    const user = userEvent.setup()
    setEngineDefault(continueOnFailure)
    renderSettingsForm()

    await user.click(failureToggle())

    expect(await screen.findByRole('option', { name: /^System default/ })).toHaveTextContent(explanation)
  })

  it('disables the settings controls in version view', () => {
    renderSettingsForm({ timeout: 60 }, true)

    expect(failureToggle()).toBeDisabled()
    expect(screen.getByRole('spinbutton', { name: 'Timeout (seconds)' })).toBeDisabled()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderSettingsForm()

    expect(await axe(container)).toHaveNoViolations()
  })
})
