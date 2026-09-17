import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { integrationsClient } from '../../../client'
import { fetchAllIntegrationModels } from '../../configuration/integrations/useAllIntegrationModels'
import { useIntegrationPermissions } from '../../configuration/integrations/useIntegrationPermissions'

import { LLMModelSelector, type LLMModelSelectorProps } from './LLMModelSelector'

vi.mock('../../../client', () => ({
  integrationsClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../configuration/integrations/useAllIntegrationModels', () => ({
  fetchAllIntegrationModels: vi.fn(),
}))

vi.mock('../../../components/FieldHelpPopover', () => ({
  FieldHelpPopover: ({ headerContent }: { headerContent?: string }) => <span>{headerContent}</span>,
}))

vi.mock('../../../components/labels/SynLabel', () => ({
  SynLabel: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

vi.mock('../../../components/SynLink', () => ({
  SynLink: ({ to, children }: { to: string; children: React.ReactNode }) => <a href={to}>{children}</a>,
}))

vi.mock('../../configuration/integrations/useIntegrationPermissions', () => ({
  useIntegrationPermissions: vi.fn(),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

const mockIntegrations = [
  { id: 'int-1', name: 'OpenAI' },
  { id: 'int-2', name: 'Anthropic' },
]

const mockModelsInt1 = [
  {
    id: 'model-1',
    integration_id: 'int-1',
    model_id: 'gpt-4o',
    name: 'GPT-4o',
    description: '128k context',
    is_default: true,
  },
  {
    id: 'model-2',
    integration_id: 'int-1',
    model_id: 'gpt-4o-mini',
    name: 'GPT-4o Mini',
    description: null,
    is_default: false,
  },
]

const mockModelsInt2 = [
  {
    id: 'model-3',
    integration_id: 'int-2',
    model_id: 'claude-sonnet-4',
    name: 'Claude Sonnet',
    description: '200k context',
    is_default: true,
  },
]

function mockClients({ integrations = mockIntegrations, isPending = false } = {}) {
  vi.mocked(integrationsClient.useQuery).mockReturnValue({
    data: { resources: integrations },
    isPending,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any)

  vi.mocked(fetchAllIntegrationModels).mockImplementation((integrationId: string) => {
    if (integrationId === 'int-1') return Promise.resolve(mockModelsInt1)
    if (integrationId === 'int-2') return Promise.resolve(mockModelsInt2)
    return Promise.resolve([])
  })
}

function renderSelector(props: Partial<LLMModelSelectorProps> = {}) {
  const defaultProps: LLMModelSelectorProps = {
    value: undefined,
    onChange: vi.fn(),
    ...props,
  }
  return render(<LLMModelSelector {...defaultProps} />, { wrapper })
}

describe('LLMModelSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    mockClients()
    vi.mocked(useIntegrationPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: false,
      canDelete: false,
      isLoading: false,
      tooltips: { create: '', update: '', enable: '', validate: '', delete: '' },
    })
  })

  it('renders with default label', () => {
    renderSelector()

    expect(screen.getByText('Model')).toBeInTheDocument()
  })

  it('renders with custom label', () => {
    renderSelector({ label: 'LLM Model' })

    expect(screen.getByText('LLM Model')).toBeInTheDocument()
  })

  it('shows empty state when no integrations exist', () => {
    mockClients({ integrations: [] })
    renderSelector()

    expect(screen.getByRole('button', { name: /model/i })).toBeInTheDocument()
  })

  it('shows guidance link when no integrations exist and user can create integrations', () => {
    vi.mocked(useIntegrationPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: false,
      canDelete: false,
      isLoading: false,
      tooltips: { create: '', update: '', enable: '', validate: '', delete: '' },
    })
    mockClients({ integrations: [] })
    renderSelector()

    const link = screen.getByRole('link', { name: /configure an LLM provider integration/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/configuration/integrations/configure')
    expect(screen.getByText(/before models can be selected/i)).toBeInTheDocument()
  })

  it('shows plain text guidance without link when user lacks integration:create permission', () => {
    vi.mocked(useIntegrationPermissions).mockReturnValue({
      canCreate: false,
      canUpdate: false,
      canDelete: false,
      isLoading: false,
      tooltips: { create: '', update: '', enable: '', validate: '', delete: '' },
    })
    mockClients({ integrations: [] })
    renderSelector()

    expect(
      screen.getByText('An administrator must configure an LLM provider integration before models can be selected.')
    ).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /configure an LLM provider integration/i })).not.toBeInTheDocument()
  })

  it('hides guidance link while permissions are loading', () => {
    vi.mocked(useIntegrationPermissions).mockReturnValue({
      canCreate: false,
      canUpdate: false,
      canDelete: false,
      isLoading: true,
      tooltips: { create: '', update: '', enable: '', validate: '', delete: '' },
    })
    mockClients({ integrations: [] })
    renderSelector()

    expect(screen.queryByRole('link', { name: /configure an LLM provider integration/i })).not.toBeInTheDocument()
    expect(screen.getByText(/An administrator must configure an LLM provider integration/i)).toBeInTheDocument()
  })

  it('calls onChange when a model is selected', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderSelector({ onChange })

    await user.click(screen.getByRole('button', { name: /model/i }))

    const option = screen.queryByText('GPT-4o')
    if (option) {
      await user.click(option)
      expect(onChange).toHaveBeenCalledWith({ llm_model_id: 'model-1' })
    }
  })

  it('displays selected model name in toggle', async () => {
    renderSelector({ value: { llm_model_id: 'model-1' } })

    await waitFor(() => {
      expect(screen.getByDisplayValue('OpenAI / GPT-4o')).toBeInTheDocument()
    })
  })

  it('falls back to UUID when selected model is not found', async () => {
    renderSelector({ value: { llm_model_id: 'unknown-uuid' } })

    await waitFor(() => {
      expect(screen.getByDisplayValue('unknown-uuid')).toBeInTheDocument()
    })
  })

  it('has no accessibility violations', async () => {
    mockClients({ integrations: [] })
    const { container } = renderSelector()

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with a selection', async () => {
    const { container } = renderSelector({ value: { llm_model_id: 'model-1' } })

    await waitFor(() => {
      expect(screen.getByDisplayValue('OpenAI / GPT-4o')).toBeInTheDocument()
    })
    expect(await axe(container)).toHaveNoViolations()
  })

  it('passes project_id to the integrations query when projectId is provided', () => {
    renderSelector({ projectId: 'proj-456' })
    expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
      params: {
        query: { integration_type: 'llm_provider', enabled: true, project_id: 'proj-456' },
      },
    })
  })

  it('does not include project_id in the query when projectId is omitted', () => {
    renderSelector()
    expect(integrationsClient.useQuery).toHaveBeenCalledWith('get', '/integrations', {
      params: {
        query: { integration_type: 'llm_provider', enabled: true },
      },
    })
  })

  describe('stale model detection', () => {
    it('calls onStaleDetected when the selected model is not in loaded models', async () => {
      const onStaleDetected = vi.fn()
      renderSelector({ value: { llm_model_id: 'nonexistent-model' }, onStaleDetected })

      await waitFor(() => {
        expect(onStaleDetected).toHaveBeenCalledOnce()
      })
    })

    it('does not call onStaleDetected when the selected model exists', async () => {
      const onStaleDetected = vi.fn()
      renderSelector({ value: { llm_model_id: 'model-1' }, onStaleDetected })

      await waitFor(() => {
        expect(screen.getByDisplayValue('OpenAI / GPT-4o')).toBeInTheDocument()
      })

      expect(onStaleDetected).not.toHaveBeenCalled()
    })

    it('does not call onStaleDetected when no model is selected', async () => {
      const onStaleDetected = vi.fn()
      renderSelector({ value: undefined, onStaleDetected })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /model/i })).toBeInTheDocument()
      })

      expect(onStaleDetected).not.toHaveBeenCalled()
    })

    it('does not call onStaleDetected while models are still loading', () => {
      mockClients({ isPending: true })
      const onStaleDetected = vi.fn()
      renderSelector({ value: { llm_model_id: 'nonexistent-model' }, onStaleDetected })

      expect(onStaleDetected).not.toHaveBeenCalled()
    })

    it('does not call onStaleDetected when a model query failed', async () => {
      vi.mocked(fetchAllIntegrationModels).mockImplementation((integrationId: string) => {
        if (integrationId === 'int-1') return Promise.resolve(mockModelsInt1)
        if (integrationId === 'int-2') return Promise.reject(new Error('network error'))
        return Promise.resolve([])
      })
      const onStaleDetected = vi.fn()
      renderSelector({ value: { llm_model_id: 'model-from-int-2' }, onStaleDetected })

      await waitFor(() => {
        expect(screen.getByDisplayValue('model-from-int-2')).toBeInTheDocument()
      })

      expect(onStaleDetected).not.toHaveBeenCalled()
    })

    it('treats a disabled model as stale', async () => {
      vi.mocked(fetchAllIntegrationModels).mockImplementation((integrationId: string) => {
        if (integrationId === 'int-1')
          return Promise.resolve([{ ...mockModelsInt1[0], id: 'disabled-model', enabled: false }])
        return Promise.resolve([])
      })
      const onStaleDetected = vi.fn()
      renderSelector({ value: { llm_model_id: 'disabled-model' }, onStaleDetected })

      await waitFor(() => {
        expect(onStaleDetected).toHaveBeenCalledOnce()
      })
    })
  })

  it('excludes disabled models from the dropdown', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchAllIntegrationModels).mockImplementation((integrationId: string) => {
      if (integrationId === 'int-1')
        return Promise.resolve([mockModelsInt1[0], { ...mockModelsInt1[1], enabled: false }])
      if (integrationId === 'int-2') return Promise.resolve(mockModelsInt2)
      return Promise.resolve([])
    })
    renderSelector()

    await user.click(screen.getByRole('button', { name: /model/i }))

    await waitFor(() => {
      expect(screen.getByText('GPT-4o')).toBeInTheDocument()
    })
    expect(screen.queryByText('GPT-4o Mini')).not.toBeInTheDocument()
    expect(screen.getByText('Claude Sonnet')).toBeInTheDocument()
  })

  it('renders only models from project-scoped integrations when projectId filters results', async () => {
    mockClients({ integrations: [mockIntegrations[0]] })
    const user = userEvent.setup()
    renderSelector({ projectId: 'proj-456' })

    await user.click(screen.getByRole('button', { name: /model/i }))

    await waitFor(() => {
      expect(screen.getByText('GPT-4o')).toBeInTheDocument()
    })
    expect(screen.queryByText('Claude Sonnet')).not.toBeInTheDocument()
  })

  it('shows all models returned by fetchAllIntegrationModels', async () => {
    const user = userEvent.setup()
    const allModels = [
      {
        id: 'p1-1',
        integration_id: 'int-large',
        model_id: 'model-a',
        name: 'Model A',
        description: null,
        is_default: false,
      },
      {
        id: 'p1-2',
        integration_id: 'int-large',
        model_id: 'model-b',
        name: 'Model B',
        description: null,
        is_default: false,
      },
      {
        id: 'p2-1',
        integration_id: 'int-large',
        model_id: 'model-c',
        name: 'Model C',
        description: null,
        is_default: true,
      },
    ]

    mockClients({ integrations: [{ id: 'int-large', name: 'BigProvider' }] })
    vi.mocked(fetchAllIntegrationModels).mockResolvedValue(allModels)

    renderSelector()

    await user.click(screen.getByRole('button', { name: /model/i }))

    await waitFor(() => {
      expect(screen.getByText('Model A')).toBeInTheDocument()
    })
    expect(screen.getByText('Model B')).toBeInTheDocument()
    expect(screen.getByText('Model C')).toBeInTheDocument()

    expect(fetchAllIntegrationModels).toHaveBeenCalledWith('int-large')
  })

  it('excludes disabled models with a single integration', async () => {
    const user = userEvent.setup()
    const modelsWithDisabled = [
      {
        id: 'model-enabled',
        integration_id: 'int-1',
        model_id: 'gpt-4o',
        name: 'GPT-4o',
        description: null,
        is_default: true,
        enabled: true,
      },
      {
        id: 'model-disabled',
        integration_id: 'int-1',
        model_id: 'gpt-3.5',
        name: 'GPT-3.5',
        description: null,
        is_default: false,
        enabled: false,
      },
    ]

    mockClients({ integrations: [{ id: 'int-1', name: 'OpenAI' }] })
    vi.mocked(fetchAllIntegrationModels).mockResolvedValue(modelsWithDisabled)

    renderSelector()

    await user.click(screen.getByRole('button', { name: /model/i }))

    await screen.findByText('GPT-4o')
    expect(screen.queryByText('GPT-3.5')).not.toBeInTheDocument()
  })
})
