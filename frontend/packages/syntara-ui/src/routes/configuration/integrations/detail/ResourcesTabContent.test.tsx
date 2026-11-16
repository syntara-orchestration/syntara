import type { IntegrationsAPI, Tool } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ResourcesTabContent } from './ResourcesTabContent'

const capturedModelsProps: Record<string, unknown> = {}
const capturedResourcesProps: Record<string, unknown> = {}

vi.mock('./IntegrationModelsTab', () => ({
  IntegrationModelsTab: (props: Record<string, unknown>) => {
    Object.assign(capturedModelsProps, props)
    return (
      <div data-testid="models-tab">
        <span data-testid="models-error">{String(props.error)}</span>
        <span data-testid="models-update-tooltip">{String(props.updateTooltip)}</span>
        <button data-testid="refetch-models" onClick={props.refetchModels as () => void}>
          Refetch
        </button>
      </div>
    )
  },
}))

vi.mock('./IntegrationResourcesTab', () => ({
  IntegrationResourcesTab: (props: Record<string, unknown>) => {
    Object.assign(capturedResourcesProps, props)
    return <div data-testid="resources-tab" />
  },
}))

const mockIntegration = {
  id: 'int-1',
  name: 'Test',
  // last_refreshed_at is a later, failed attempt; last_successful_refresh_at is the older success.
  last_refreshed_at: '2024-06-01T00:00:00Z',
  last_successful_refresh_at: '2024-01-01T00:00:00Z',
  refresh_status: 'warning',
  refresh_error: 'Default model no longer offered',
} as IntegrationsAPI.components['schemas']['IntegrationRead']

function createModelsState(overrides: Record<string, unknown> = {}) {
  return {
    models: [],
    isLoading: false,
    error: null,
    refetchModels: vi.fn().mockResolvedValue(undefined),
    enabledModelIds: new Set<string>(),
    enabledCount: 0,
    allSelected: false,
    isDirty: false,
    isSaving: false,
    handleSave: vi.fn(),
    handleSelectAll: vi.fn(),
    defaultModelId: null,
    handleSelectWithDefaultClear: vi.fn(),
    handleSetDefault: vi.fn(),
    handleRemoveDefault: vi.fn(),
    resetSelectionToServer: vi.fn(),
    resetDefault: vi.fn(),
    ...overrides,
  }
}

const defaultProps = {
  integration: mockIntegration,
  modelsState: createModelsState(),
  tools: [],
  enabledToolIds: new Set<string>(),
  toolEnabledCount: 0,
  handleSelectTool: vi.fn(),
  refetchTools: vi.fn().mockResolvedValue(undefined),
  onRefreshed: vi.fn().mockResolvedValue(undefined),
  canUpdate: true,
}

describe('ResourcesTabContent', () => {
  it('renders IntegrationModelsTab when isLLM is true', () => {
    render(<ResourcesTabContent {...defaultProps} isLLM />)

    expect(screen.getByTestId('models-tab')).toBeInTheDocument()
    expect(screen.queryByTestId('resources-tab')).not.toBeInTheDocument()
  })

  it('renders IntegrationResourcesTab when isLLM is false', () => {
    render(<ResourcesTabContent {...defaultProps} isLLM={false} />)

    expect(screen.getByTestId('resources-tab')).toBeInTheDocument()
    expect(screen.queryByTestId('models-tab')).not.toBeInTheDocument()
  })

  it('forwards refetchModels to IntegrationModelsTab', async () => {
    const modelsState = createModelsState()
    const user = userEvent.setup()
    render(<ResourcesTabContent {...defaultProps} modelsState={modelsState} isLLM />)

    await user.click(screen.getByTestId('refetch-models'))

    expect(modelsState.refetchModels).toHaveBeenCalled()
  })

  it('passes null error when modelsState.error is null', () => {
    render(<ResourcesTabContent {...defaultProps} modelsState={createModelsState({ error: null })} isLLM />)

    expect(screen.getByTestId('models-error')).toHaveTextContent('null')
  })

  it('passes error message when modelsState.error has message', () => {
    render(
      <ResourcesTabContent
        {...defaultProps}
        modelsState={createModelsState({ error: new Error('Connection failed') })}
        isLLM
      />
    )

    expect(screen.getByTestId('models-error')).toHaveTextContent('Connection failed')
  })

  it('passes updateTooltip when provided', () => {
    render(<ResourcesTabContent {...defaultProps} isLLM updateTooltip="You lack permission" />)

    expect(screen.getByTestId('models-update-tooltip')).toHaveTextContent('You lack permission')
  })

  it('passes undefined updateTooltip when not provided', () => {
    render(<ResourcesTabContent {...defaultProps} isLLM />)

    expect(screen.getByTestId('models-update-tooltip')).toHaveTextContent('undefined')
  })

  it('forwards canUpdate=false to child component', () => {
    render(<ResourcesTabContent {...defaultProps} isLLM canUpdate={false} />)

    expect(capturedModelsProps.canUpdate).toBe(false)
  })

  it('forwards tool props to IntegrationResourcesTab', () => {
    const tools = [{ id: 't1', name: 'tool1' }] as Tool[]
    const enabledToolIds = new Set(['t1'])
    render(
      <ResourcesTabContent
        {...defaultProps}
        isLLM={false}
        tools={tools}
        enabledToolIds={enabledToolIds}
        toolEnabledCount={1}
      />
    )

    expect(capturedResourcesProps.tools).toBe(tools)
    expect(capturedResourcesProps.enabledToolIds).toBe(enabledToolIds)
    expect(capturedResourcesProps.enabledCount).toBe(1)
  })

  it('forwards all model props to IntegrationModelsTab', () => {
    const modelsState = createModelsState({
      models: [{ id: 'm1' }],
      isLoading: true,
      enabledModelIds: new Set(['m1']),
      enabledCount: 1,
      allSelected: true,
      defaultModelId: 'm1',
    })
    render(<ResourcesTabContent {...defaultProps} modelsState={modelsState} isLLM canUpdate={false} />)

    expect(capturedModelsProps.integrationId).toBe('int-1')
    expect(capturedModelsProps.models).toBe(modelsState.models)
    expect(capturedModelsProps.isLoading).toBe(true)
    expect(capturedModelsProps.enabledModelIds).toBe(modelsState.enabledModelIds)
    expect(capturedModelsProps.enabledCount).toBe(1)
    expect(capturedModelsProps.allSelected).toBe(true)
    expect(capturedModelsProps.defaultModelId).toBe('m1')
    expect(capturedModelsProps.handleSelectAll).toBe(modelsState.handleSelectAll)
    expect(capturedModelsProps.handleSelectWithDefaultClear).toBe(modelsState.handleSelectWithDefaultClear)
    expect(capturedModelsProps.handleSetDefault).toBe(modelsState.handleSetDefault)
    expect(capturedModelsProps.handleRemoveDefault).toBe(modelsState.handleRemoveDefault)
    expect(capturedModelsProps.resetSelectionToServer).toBe(modelsState.resetSelectionToServer)
    expect(capturedModelsProps.resetDefault).toBe(modelsState.resetDefault)
    // The displayed timestamp is the last SUCCESSFUL refresh, not the later failed attempt.
    expect(capturedModelsProps.lastRefreshedAt).toBe('2024-01-01T00:00:00Z')
    expect(capturedModelsProps.refreshStatus).toBe('warning')
    expect(capturedModelsProps.refreshError).toBe('Default model no longer offered')
    expect(capturedModelsProps.canUpdate).toBe(false)
    expect(capturedModelsProps.onRefreshed).toBe(defaultProps.onRefreshed)
  })

  it('forwards all tool props to IntegrationResourcesTab', () => {
    const tools = [
      { id: 't1', name: 'tool1' },
      { id: 't2', name: 'tool2' },
    ] as Tool[]
    const enabledToolIds = new Set(['t1'])
    const handleSelectTool = vi.fn()
    const refetchTools = vi.fn().mockResolvedValue(undefined)
    const onRefreshed = vi.fn().mockResolvedValue(undefined)

    render(
      <ResourcesTabContent
        {...defaultProps}
        isLLM={false}
        tools={tools}
        enabledToolIds={enabledToolIds}
        toolEnabledCount={1}
        handleSelectTool={handleSelectTool}
        refetchTools={refetchTools}
        onRefreshed={onRefreshed}
        canUpdate={false}
      />
    )

    expect(capturedResourcesProps.integrationId).toBe('int-1')
    expect(capturedResourcesProps.tools).toBe(tools)
    expect(capturedResourcesProps.enabledToolIds).toBe(enabledToolIds)
    expect(capturedResourcesProps.enabledCount).toBe(1)
    expect(capturedResourcesProps.handleSelectTool).toBe(handleSelectTool)
    // The displayed timestamp is the last SUCCESSFUL refresh, not the later failed attempt.
    expect(capturedResourcesProps.lastRefreshedAt).toBe('2024-01-01T00:00:00Z')
    expect(capturedResourcesProps.canUpdate).toBe(false)
    expect(capturedResourcesProps.onRefreshed).toBe(onRefreshed)
    expect(capturedResourcesProps.refetchTools).toBe(refetchTools)
  })

  it('passes null when modelsState.error has no message property', () => {
    const errorWithoutMessage = { name: 'Error' } as unknown as Error
    render(
      <ResourcesTabContent {...defaultProps} modelsState={createModelsState({ error: errorWithoutMessage })} isLLM />
    )

    expect(screen.getByTestId('models-error')).toHaveTextContent('null')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ResourcesTabContent {...defaultProps} isLLM={false} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
