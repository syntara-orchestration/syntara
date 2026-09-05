import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReactFlowProvider } from '@xyflow/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createManualTrigger, useWorkflowStore } from '../../stores/useWorkflowStore'
import { TriggerNodeComponent } from '../workflows/canvas/nodes/TriggerNode'

// Mock deleteElements to track calls
const mockDeleteElements = vi.fn()
vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual('@xyflow/react')
  return {
    ...actual,
    useReactFlow: () => ({
      deleteElements: mockDeleteElements,
    }),
  }
})

// Helper to wrap component with required providers
function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <ReactFlowProvider>{ui}</ReactFlowProvider>
    </QueryClientProvider>
  )
}

// Create mock node props for TriggerNodeComponent
function createMockTriggerNodeProps(id: string, name: string, details: string | null = 'Manual') {
  return {
    id,
    type: 'trigger' as const,
    data: { name, details },
    dragging: false,
    selected: false,
    isConnectable: true,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    zIndex: 0,
    selectable: true,
    deletable: true,
    draggable: true,
  }
}

describe('Trigger Node Kebab Menu Delete', () => {
  beforeEach(() => {
    // Reset workflow store before each test
    useWorkflowStore.getState().setWorkflow(null)
    vi.clearAllMocks()
  })

  it('renders trigger node with kebab menu button', () => {
    // Setup workflow with a trigger
    const trigger = createManualTrigger('trigger-1')
    useWorkflowStore.getState().setWorkflow({
      schema_version: '2.0.0' as const,
      name: 'Test',
      triggers: [trigger],
      workflow: { activities: [] },
    })

    const props = createMockTriggerNodeProps('trigger-0', 'Trigger', 'Manual')

    renderWithProviders(<TriggerNodeComponent {...props} />)

    // Verify the node renders with the correct title
    expect(screen.getByText('Trigger')).toBeInTheDocument()

    // Verify the kebab menu button is present
    expect(screen.getByRole('button', { name: /step actions menu/i })).toBeInTheDocument()
  })

  it('opens dropdown menu when kebab button is clicked', async () => {
    const user = userEvent.setup()

    // Setup workflow with a trigger
    const trigger = createManualTrigger('trigger-1')
    useWorkflowStore.getState().setWorkflow({
      schema_version: '2.0.0' as const,
      name: 'Test',
      triggers: [trigger],
      workflow: { activities: [] },
    })

    const props = createMockTriggerNodeProps('trigger-0', 'Trigger', 'Manual')

    renderWithProviders(<TriggerNodeComponent {...props} />)

    // Click the kebab menu button
    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    // Verify the dropdown menu opens and shows the Delete option
    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
    })
  })

  it('deletes trigger when Delete menu item is clicked', async () => {
    const user = userEvent.setup()

    // Setup workflow with two triggers
    const trigger1 = createManualTrigger('trigger-1')
    const trigger2 = createManualTrigger('trigger-2', true)
    useWorkflowStore.getState().setWorkflow({
      schema_version: '2.0.0' as const,
      name: 'Test',
      triggers: [trigger1, trigger2],
      workflow: { activities: [] },
    })

    const props = createMockTriggerNodeProps('trigger-0', 'Trigger', 'Manual')

    renderWithProviders(<TriggerNodeComponent {...props} />)

    // Click the kebab menu button
    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    // Wait for menu to open and click Delete
    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
    })

    const deleteButton = screen.getByRole('menuitem', { name: 'Delete' })
    await user.click(deleteButton)

    // Verify deleteElements was called with correct trigger node id
    // This triggers React Flow's onNodesDelete which handles proper cleanup
    await waitFor(() => {
      expect(mockDeleteElements).toHaveBeenCalledWith({ nodes: [{ id: 'trigger-0' }] })
    })
  })

  it('applies danger styling to Delete menu item', async () => {
    const user = userEvent.setup()

    // Setup workflow with a trigger
    const trigger = createManualTrigger('trigger-1')
    useWorkflowStore.getState().setWorkflow({
      schema_version: '2.0.0' as const,
      name: 'Test',
      triggers: [trigger],
      workflow: { activities: [] },
    })

    const props = createMockTriggerNodeProps('trigger-0', 'Trigger', 'Manual')

    renderWithProviders(<TriggerNodeComponent {...props} />)

    // Click the kebab menu button
    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    // PF6 wraps menuitems in <li role="none">, which is invisible to ARIA queries.
    // innerHTML is the only way to assert danger styling without banned DOM traversal.
    // TODO: revisit if PF6 exposes a semantic hook for menuitem danger state in future.
    await waitFor(() => {
      expect(screen.getByRole('menu').innerHTML).toContain('pf-m-danger')
    })
  })

  it('prevents click propagation from menu trigger to node', async () => {
    const user = userEvent.setup()

    // Setup workflow with a trigger
    const trigger = createManualTrigger('trigger-1')
    useWorkflowStore.getState().setWorkflow({
      schema_version: '2.0.0' as const,
      name: 'Test',
      triggers: [trigger],
      workflow: { activities: [] },
    })

    const props = createMockTriggerNodeProps('trigger-0', 'Trigger', 'Manual')

    // Track if the parent was clicked (would happen in ReactFlow for node selection)
    let parentClicked = false

    render(
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: { queries: { retry: false } },
          })
        }
      >
        <ReactFlowProvider>
          {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions */}
          <div onClick={() => (parentClicked = true)}>
            <TriggerNodeComponent {...props} />
          </div>
        </ReactFlowProvider>
      </QueryClientProvider>
    )

    // Click the kebab menu button
    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    // Parent should NOT have been clicked due to stopPropagation
    expect(parentClicked).toBe(false)
  })
})
