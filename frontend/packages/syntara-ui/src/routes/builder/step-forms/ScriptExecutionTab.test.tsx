import { ExecutorTypeEnum } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { FormProvider, useForm, type UseFormReturn } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AppRoute } from '../../../app/AppRoute'
import { useExecutionTargetPermissions } from '../../execution-plane/useExecutionTargetPermissions'
import { ScriptAffinityEnum } from '../utils/scriptExecutionProfile'

import { actionFormSchema, type ActionFormValues } from './actionFormSchema'
import { CLEAR_UNAVAILABLE_TARGET_LABEL, ScriptExecutionTab, UNAVAILABLE_TARGET_ERROR } from './ScriptExecutionTab'
import { useAllEnabledExecutionTargets } from './useAllEnabledExecutionTargets'

const UNAVAILABLE_TARGET_ID = '550e8400-e29b-41d4-a716-446655440099'

function expectScriptFormValid(values: ActionFormValues) {
  const result = actionFormSchema.safeParse(values)
  expect(result.success, result.success ? undefined : JSON.stringify(result.error.issues)).toBe(true)
}

function expectRequiredTargetMissing(values: ActionFormValues) {
  const result = actionFormSchema.safeParse(values)
  expect(result.success).toBe(false)
  if (result.success) return
  expect(result.error.issues).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        path: ['execution_target_id'],
        message: 'Execution target is required',
      }),
    ])
  )
}

vi.mock('./useAllEnabledExecutionTargets', () => ({
  useAllEnabledExecutionTargets: vi.fn(),
}))

const allowedExecutionTargetPermissions = {
  canRead: true,
  canCreate: true,
  canUpdate: true,
  canDelete: true,
  isLoading: false,
  tooltips: {
    read: 'To list execution targets, you need a role with the execution_target:read policy. Contact your Admin to request access.',
    create: '',
    update: '',
    enable: '',
    delete: '',
  },
}

vi.mock('../../execution-plane/useExecutionTargetPermissions', () => ({
  useExecutionTargetPermissions: vi.fn(() => allowedExecutionTargetPermissions),
}))

vi.mock('../VersionViewContext', () => ({
  useIsVersionView: () => false,
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function renderTab(defaultValues?: Partial<ActionFormValues>) {
  let form: UseFormReturn<ActionFormValues> | undefined

  function Wrapper({ children }: { children: ReactNode }) {
    const methods = useForm<ActionFormValues>({
      defaultValues: {
        name: 'Script',
        executor: 'script',
        affinity: ScriptAffinityEnum.NONE,
        ...defaultValues,
      },
    })
    form = methods
    return (
      <QueryClientProvider client={queryClient}>
        <FormProvider {...methods}>{children}</FormProvider>
      </QueryClientProvider>
    )
  }

  const view = render(
    <Wrapper>
      <ScriptExecutionTab />
    </Wrapper>
  )

  if (!form) {
    throw new Error('Expected form methods to be initialized')
  }

  return { ...view, form }
}

describe('ScriptExecutionTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    vi.mocked(useExecutionTargetPermissions).mockReturnValue(allowedExecutionTargetPermissions)
    vi.mocked(useAllEnabledExecutionTargets).mockReturnValue({
      targets: [
        { id: 'target-1', name: 'worker-central-01' },
        { id: 'target-2', name: 'worker-west-01' },
      ] as never,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
  })

  it('renders affinity with none selected by default and hides the target select', () => {
    renderTab()

    expect(screen.getByText('Choose where this step runs on the execution plane.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Affinity' })).toHaveTextContent('None')
    expect(screen.queryByRole('button', { name: 'Execution target' })).not.toBeInTheDocument()
  })

  it('shows the execution target select when Required target is chosen', async () => {
    const user = userEvent.setup()
    renderTab()

    await user.click(screen.getByRole('button', { name: 'Affinity' }))
    await user.click(screen.getByRole('option', { name: /Required target/i }))

    expect(screen.getByRole('button', { name: 'Execution target' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Execution target' }))
    expect(screen.getByRole('option', { name: 'worker-central-01' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'worker-west-01' })).toBeInTheDocument()
  })

  it('shows empty guidance with a new-tab configure CTA when required target has no targets', () => {
    vi.mocked(useAllEnabledExecutionTargets).mockReturnValue({
      targets: [],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    renderTab({ affinity: ScriptAffinityEnum.REQUIRED_TARGET })

    expect(screen.getByText('No execution targets yet')).toBeInTheDocument()
    const configureLink = screen.getByRole('link', {
      name: 'Configure execution target (opens in a new tab)',
    })
    expect(configureLink).toHaveAttribute('href', AppRoute.ExecutionPlane.Create)
    expect(configureLink).toHaveAttribute('target', '_blank')
    expect(configureLink).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('shows an error state with retry when loading targets fails', async () => {
    const refetch = vi.fn().mockResolvedValue(undefined)
    vi.mocked(useAllEnabledExecutionTargets).mockReturnValue({
      targets: [],
      isLoading: false,
      isError: true,
      error: Object.assign(new Error('Network failure'), { status: 500, retryable: true }),
      refetch,
    })
    const user = userEvent.setup()
    renderTab({ affinity: ScriptAffinityEnum.REQUIRED_TARGET })

    expect(screen.getByText('Error loading execution targets')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalledOnce()
  })

  it('disables Required target in the affinity menu without execution_target:read', async () => {
    vi.mocked(useExecutionTargetPermissions).mockReturnValue({
      ...allowedExecutionTargetPermissions,
      canRead: false,
      canCreate: false,
      canUpdate: false,
      canDelete: false,
    })
    const user = userEvent.setup()
    renderTab()

    await user.click(screen.getByRole('button', { name: 'Affinity' }))
    const requiredOption = screen.getByRole('option', { name: /Required target/i })
    expect(requiredOption).toBeDisabled()
    expect(requiredOption).toHaveTextContent(/execution_target:read/)
    expect(useAllEnabledExecutionTargets).not.toHaveBeenCalled()
  })

  it('disables the Affinity select while permissions are still loading', () => {
    vi.mocked(useExecutionTargetPermissions).mockReturnValue({
      ...allowedExecutionTargetPermissions,
      canRead: false,
      isLoading: true,
    })
    renderTab()

    expect(screen.getByRole('button', { name: 'Affinity' })).toBeDisabled()
    expect(useAllEnabledExecutionTargets).not.toHaveBeenCalled()
  })

  it('shows an access explanation and skips the list request when Required target is set without read', () => {
    const readDeniedMessage = allowedExecutionTargetPermissions.tooltips.read
    vi.mocked(useExecutionTargetPermissions).mockReturnValue({
      ...allowedExecutionTargetPermissions,
      canRead: false,
      canCreate: false,
      canUpdate: false,
      canDelete: false,
    })
    renderTab({ affinity: ScriptAffinityEnum.REQUIRED_TARGET })

    expect(screen.getByText('Cannot list execution targets')).toBeInTheDocument()
    expect(screen.getByText(readDeniedMessage)).toBeInTheDocument()
    expect(useAllEnabledExecutionTargets).not.toHaveBeenCalled()
  })

  it('shows a saved disabled target as unavailable without clearing it on mount', async () => {
    const user = userEvent.setup()
    const { form } = renderTab({
      affinity: ScriptAffinityEnum.REQUIRED_TARGET,
      execution_target_id: UNAVAILABLE_TARGET_ID,
    })

    expect(screen.getByRole('button', { name: 'Execution target' })).toHaveTextContent('Unavailable execution target')
    expect(screen.getByText(UNAVAILABLE_TARGET_ERROR)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: CLEAR_UNAVAILABLE_TARGET_LABEL })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Affinity' })).toHaveTextContent('Required target')
    // Viewing must not wipe the saved ID (that left REQUIRED_TARGET + empty → silent save failure).
    expect(form.getValues('execution_target_id')).toBe(UNAVAILABLE_TARGET_ID)
    expect(form.getValues('affinity')).toBe(ScriptAffinityEnum.REQUIRED_TARGET)
    expectScriptFormValid(form.getValues())

    await user.click(screen.getByRole('button', { name: 'Execution target' }))
    expect(screen.getByRole('option', { name: /Unavailable execution target/i })).toBeDisabled()
    expect(screen.getByRole('option', { name: 'worker-central-01' })).toBeInTheDocument()

    await user.click(screen.getByRole('option', { name: 'worker-central-01' }))
    expect(screen.getByRole('button', { name: 'Execution target' })).toHaveTextContent('worker-central-01')
    expect(screen.queryByText(UNAVAILABLE_TARGET_ERROR)).not.toBeInTheDocument()
  })

  it('clears an unavailable target only when the alert action is clicked', async () => {
    const user = userEvent.setup()
    vi.mocked(useAllEnabledExecutionTargets).mockReturnValue({
      targets: [],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    const { form } = renderTab({
      affinity: ScriptAffinityEnum.REQUIRED_TARGET,
      execution_target_id: UNAVAILABLE_TARGET_ID,
    })

    expect(screen.getByText(UNAVAILABLE_TARGET_ERROR)).toBeInTheDocument()
    expect(screen.getByText('No execution targets yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Affinity' })).toHaveTextContent('Required target')
    // Regression: mount must not auto-clear into REQUIRED_TARGET with a missing target
    // (that made Save/Update fail with no visible error on other tabs).
    expect(form.getValues('execution_target_id')).toBe(UNAVAILABLE_TARGET_ID)
    expect(form.getValues('affinity')).toBe(ScriptAffinityEnum.REQUIRED_TARGET)
    expectScriptFormValid(form.getValues())

    await user.click(screen.getByRole('button', { name: CLEAR_UNAVAILABLE_TARGET_LABEL }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Affinity' })).toHaveTextContent('None')
    })
    expect(form.getValues('affinity')).toBe(ScriptAffinityEnum.NONE)
    expect(form.getValues('execution_target_id')).toBeUndefined()
    expectScriptFormValid(form.getValues())
    // Contrast: clearing the ID while leaving Required target would block save.
    expectRequiredTargetMissing({
      executor: ExecutorTypeEnum.SCRIPT,
      name: 'Script',
      affinity: ScriptAffinityEnum.REQUIRED_TARGET,
      execution_target_id: undefined,
    })
    expect(screen.queryByText(UNAVAILABLE_TARGET_ERROR)).not.toBeInTheDocument()
    expect(screen.queryByText('No execution targets yet')).not.toBeInTheDocument()
  })

  describe('accessibility', () => {
    it('has no violations with the execution target select', async () => {
      const { container } = renderTab({ affinity: ScriptAffinityEnum.REQUIRED_TARGET })
      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no violations for the access-denied alert', async () => {
      vi.mocked(useExecutionTargetPermissions).mockReturnValue({
        ...allowedExecutionTargetPermissions,
        canRead: false,
        canCreate: false,
        canUpdate: false,
        canDelete: false,
      })
      const { container } = renderTab({ affinity: ScriptAffinityEnum.REQUIRED_TARGET })

      expect(screen.getByText('Cannot list execution targets')).toBeInTheDocument()
      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no violations for empty state with unavailable-target warning', async () => {
      vi.mocked(useAllEnabledExecutionTargets).mockReturnValue({
        targets: [],
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })
      const { container } = renderTab({
        affinity: ScriptAffinityEnum.REQUIRED_TARGET,
        execution_target_id: UNAVAILABLE_TARGET_ID,
      })

      expect(screen.getByText(UNAVAILABLE_TARGET_ERROR)).toBeInTheDocument()
      expect(screen.getByText('No execution targets yet')).toBeInTheDocument()
      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no violations while permissions are loading', async () => {
      vi.mocked(useExecutionTargetPermissions).mockReturnValue({
        ...allowedExecutionTargetPermissions,
        canRead: false,
        isLoading: true,
      })
      const { container } = renderTab({ affinity: ScriptAffinityEnum.REQUIRED_TARGET })

      expect(screen.getByLabelText('Checking execution target permissions')).toBeInTheDocument()
      expect(await axe(container)).toHaveNoViolations()
    })
  })
})
