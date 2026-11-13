import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ScriptAffinityEnum } from '../utils/scriptExecutionProfile'

import type { ActionFormValues } from './actionFormSchema'
import { ScriptExecutionTab } from './ScriptExecutionTab'
import { useAllEnabledExecutionTargets } from './useAllEnabledExecutionTargets'

const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}))

vi.mock('./useAllEnabledExecutionTargets', () => ({
  useAllEnabledExecutionTargets: vi.fn(),
}))

vi.mock('../../execution-plane/useExecutionTargetPermissions', () => ({
  useExecutionTargetPermissions: vi.fn(() => ({
    canCreate: true,
    canUpdate: true,
    canDelete: true,
    isLoading: false,
    tooltips: {
      create: '',
      update: '',
      enable: '',
      delete: '',
    },
  })),
}))

vi.mock('../VersionViewContext', () => ({
  useIsVersionView: () => false,
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function renderTab(defaultValues?: Partial<ActionFormValues>) {
  function Wrapper({ children }: { children: ReactNode }) {
    const methods = useForm<ActionFormValues>({
      defaultValues: {
        name: 'Script',
        executor: 'script',
        affinity: ScriptAffinityEnum.NONE,
        ...defaultValues,
      },
    })
    return (
      <QueryClientProvider client={queryClient}>
        <FormProvider {...methods}>{children}</FormProvider>
      </QueryClientProvider>
    )
  }

  return render(
    <Wrapper>
      <ScriptExecutionTab />
    </Wrapper>
  )
}

describe('ScriptExecutionTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
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

  it('shows empty guidance with configure CTA when required target has no targets', async () => {
    vi.mocked(useAllEnabledExecutionTargets).mockReturnValue({
      targets: [],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    const user = userEvent.setup()
    renderTab({ affinity: ScriptAffinityEnum.REQUIRED_TARGET })

    expect(screen.getByText('No execution targets yet')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Configure execution target' }))
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/execution-plane/create' })
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

    expect(screen.getByTestId('error-state')).toBeInTheDocument()
    expect(screen.getByText('Error loading execution targets')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalledOnce()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderTab({ affinity: ScriptAffinityEnum.REQUIRED_TARGET })
    expect(await axe(container)).toHaveNoViolations()
  })
})
