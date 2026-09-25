import { zodResolver } from '@hookform/resolvers/zod'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { z } from 'zod'

import { useWorkflowEngineDefaults } from '../../hooks/useWorkflowEngineDefaults'

import { NodeSettingsForm } from './NodeSettingsForm'
import { nodeSettingsSchema } from './nodeSettingsSchema'

const mockDefaults = {
  continueOnFailure: false,
  timeoutSeconds: { script: 300, agentic: 300, aap: 3600, approval: 86400, http_request: 30 },
  retry: { maxRetries: 3, initialInterval: 1, maxInterval: 60, backoffCoefficient: 2 },
  maxLoopIterations: 10000,
  convergeWaitDuration: null,
}

vi.mock('../../hooks/useWorkflowEngineDefaults', () => ({
  useWorkflowEngineDefaults: vi.fn(() => ({ defaults: null, isLoading: false })),
}))

const testSchema = z.object({ settings: nodeSettingsSchema })
type TestFormData = z.infer<typeof testSchema>

function Wrapper({ children, defaultValues }: { children: React.ReactNode; defaultValues?: Partial<TestFormData> }) {
  const methods = useForm<TestFormData>({
    resolver: zodResolver(testSchema),
    defaultValues: { settings: {}, ...defaultValues },
  })
  return (
    <FormProvider {...methods}>
      <form>{children}</form>
    </FormProvider>
  )
}

function setup(props: React.ComponentProps<typeof NodeSettingsForm> = {}, defaultValues?: Partial<TestFormData>) {
  const user = userEvent.setup()
  const view = render(
    <Wrapper defaultValues={defaultValues}>
      <NodeSettingsForm {...props} />
    </Wrapper>
  )
  return { user, ...view }
}

const cofToggle = () => screen.getByRole('button', { name: 'On failure behavior' })

describe('NodeSettingsForm', () => {
  describe('continue_on_failure', () => {
    it('renders the behavior dropdown', () => {
      setup()
      expect(cofToggle()).toBeInTheDocument()
    })

    it('shows System default when value is undefined', () => {
      setup()
      expect(cofToggle()).toHaveTextContent('System default')
    })

    it('shows Continue on failure when value is true', () => {
      setup({}, { settings: { continue_on_failure: true } })
      expect(cofToggle()).toHaveTextContent('Continue on failure')
    })

    it('shows Stop workflow or branch on failure when value is false', () => {
      setup({}, { settings: { continue_on_failure: false } })
      expect(cofToggle()).toHaveTextContent('Stop workflow or branch on failure')
    })

    it('switches to Continue on failure when selected', async () => {
      const { user } = setup()
      await user.click(cofToggle())
      await waitFor(() => expect(screen.getByText('Continue on failure')).toBeVisible())
      await user.click(screen.getByText('Continue on failure'))
      await waitFor(() => expect(cofToggle()).toHaveTextContent('Continue on failure'))
    })

    it('switches back to System default when selected', async () => {
      const { user } = setup({}, { settings: { continue_on_failure: true } })
      await user.click(cofToggle())
      await waitFor(() => expect(screen.getByRole('option', { name: /System default/i })).toBeVisible())
      await user.click(screen.getByRole('option', { name: /System default/i }))
      await waitFor(() => expect(cofToggle()).toHaveTextContent('System default'))
    })

    it('does not render when supportsContinueOnFailure is false', () => {
      setup({ supportsContinueOnFailure: false })
      expect(screen.queryByRole('button', { name: 'On failure behavior' })).not.toBeInTheDocument()
    })

    it('renders custom help text when provided', () => {
      setup({ continueOnFailureHelp: 'Custom help text here' })
      expect(screen.getByText('Custom help text here')).toBeInTheDocument()
    })
  })

  describe('timeout', () => {
    it('renders a seconds input when timeoutFormat is seconds', () => {
      setup({ timeoutFormat: 'seconds' })
      expect(screen.getByRole('spinbutton', { name: 'Timeout (seconds)' })).toBeInTheDocument()
    })

    it('renders duration picker when timeoutFormat is duration', () => {
      setup({ timeoutFormat: 'duration' })
      expect(screen.getByRole('spinbutton', { name: 'Days' })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: 'Hours' })).toBeInTheDocument()
    })

    it('does not render timeout when supportsTimeout is false', () => {
      setup({ supportsTimeout: false })
      expect(screen.queryByRole('spinbutton', { name: 'Timeout (seconds)' })).not.toBeInTheDocument()
    })

    it('clears timeout to undefined when the seconds input is emptied', async () => {
      const { user } = setup({ timeoutFormat: 'seconds' }, { settings: { timeout: 30 } })
      const input = screen.getByRole('spinbutton', { name: 'Timeout (seconds)' })
      await user.clear(input)
      expect(input).toHaveValue(null)
    })
  })

  describe('retry policy', () => {
    it('renders the override retry policy toggle', () => {
      setup()
      expect(screen.getByRole('switch', { name: 'Override retry policy' })).toBeInTheDocument()
    })

    it('does not render retry fields when override is off', () => {
      setup()
      expect(screen.queryByRole('spinbutton', { name: 'Max retries' })).not.toBeInTheDocument()
    })

    it('shows retry fields after enabling override', async () => {
      const { user } = setup()
      await user.click(screen.getByRole('switch', { name: 'Override retry policy' }))
      await waitFor(() => {
        expect(screen.getByRole('spinbutton', { name: 'Max retries' })).toBeInTheDocument()
      })
    })

    it('hides retry fields again after disabling override', async () => {
      const { user } = setup()
      await user.click(screen.getByRole('switch', { name: 'Override retry policy' }))
      await waitFor(() => {
        expect(screen.getByRole('spinbutton', { name: 'Max retries' })).toBeInTheDocument()
      })
      await user.click(screen.getByRole('switch', { name: 'Override retry policy' }))
      await waitFor(() => {
        expect(screen.queryByRole('spinbutton', { name: 'Max retries' })).not.toBeInTheDocument()
      })
    })

    it('does not render retry policy when supportsRetryPolicy is false', () => {
      setup({ supportsRetryPolicy: false })
      expect(screen.queryByRole('switch', { name: 'Override retry policy' })).not.toBeInTheDocument()
    })
  })

  describe('with non-null system defaults', () => {
    beforeEach(() => {
      vi.mocked(useWorkflowEngineDefaults).mockReturnValue({ defaults: mockDefaults, isLoading: false })
    })

    it('shows system default label in the CoF dropdown description', async () => {
      const { user } = setup()
      await user.click(cofToggle())
      expect(await screen.findByRole('option', { name: /System default/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /System default/i })).toHaveTextContent(
        'system default: stop on failure'
      )
    })

    it('shows system default in timeout placeholder', () => {
      setup({ timeoutFormat: 'seconds', timeoutNodeType: 'script' })
      expect(screen.getByRole('spinbutton', { name: 'Timeout (seconds)' })).toHaveAttribute(
        'placeholder',
        '300 — system default'
      )
    })

    it('shows system default in retry field placeholders when override is enabled', async () => {
      const { user } = setup()
      await user.click(screen.getByRole('switch', { name: 'Override retry policy' }))
      expect(await screen.findByRole('spinbutton', { name: 'Max retries' })).toBeInTheDocument()
      expect(screen.getByRole('spinbutton', { name: 'Max retries' })).toHaveAttribute(
        'placeholder',
        '3 — system default'
      )
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = setup()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with retry policy expanded', async () => {
    const { user, container } = setup()
    await user.click(screen.getByRole('switch', { name: 'Override retry policy' }))
    await waitFor(() => {
      expect(screen.getByRole('spinbutton', { name: 'Max retries' })).toBeInTheDocument()
    })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  describe('with continueOnFailure=true system default', () => {
    beforeEach(() => {
      vi.mocked(useWorkflowEngineDefaults).mockReturnValue({
        defaults: { ...mockDefaults, continueOnFailure: true },
        isLoading: false,
      })
    })

    it('shows "continue on failure" in system default description', async () => {
      const { user } = setup()
      await user.click(cofToggle())
      const option = await screen.findByRole('option', { name: /System default/i })
      expect(option).toHaveTextContent('system default: continue on failure')
    })
  })

  describe('duration timeout with system defaults', () => {
    beforeEach(() => {
      vi.mocked(useWorkflowEngineDefaults).mockReturnValue({ defaults: mockDefaults, isLoading: false })
    })

    it('shows formatted system default in duration help text', () => {
      setup({ timeoutFormat: 'duration', timeoutNodeType: 'approval' })
      expect(screen.getByText(/System default: 1d/)).toBeInTheDocument()
    })

    it('shows fallback text when no system default', () => {
      vi.mocked(useWorkflowEngineDefaults).mockReturnValue({ defaults: null, isLoading: false })
      setup({ timeoutFormat: 'duration' })
      expect(screen.getByText(/Falls back to system default if not set/)).toBeInTheDocument()
    })
  })

  describe('retry policy with system defaults', () => {
    beforeEach(() => {
      vi.mocked(useWorkflowEngineDefaults).mockReturnValue({ defaults: mockDefaults, isLoading: false })
    })

    it('shows system default info in retry help text', () => {
      setup()
      expect(screen.getByText(/3 retries, 1s initial interval/)).toBeInTheDocument()
    })

    it('shows generic help text when no system defaults', () => {
      vi.mocked(useWorkflowEngineDefaults).mockReturnValue({ defaults: null, isLoading: false })
      setup()
      expect(screen.getByText('When disabled, the system default retry policy applies.')).toBeInTheDocument()
    })
  })

  describe('all sections disabled', () => {
    it('renders empty form when all sections are disabled', () => {
      setup({ supportsContinueOnFailure: false, supportsTimeout: false, supportsRetryPolicy: false })
      expect(screen.queryByRole('button', { name: 'On failure behavior' })).not.toBeInTheDocument()
      expect(screen.queryByRole('spinbutton', { name: 'Timeout (seconds)' })).not.toBeInTheDocument()
      expect(screen.queryByRole('switch', { name: 'Override retry policy' })).not.toBeInTheDocument()
    })
  })
})
