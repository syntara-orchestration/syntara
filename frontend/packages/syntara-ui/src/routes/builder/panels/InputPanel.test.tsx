import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ColorSchemeProvider } from '../../../providers/theme/ColorSchemeProvider'

import { InputPanel } from './InputPanel'

function renderWithProvider(ui: React.ReactElement) {
  return render(<ColorSchemeProvider>{ui}</ColorSchemeProvider>)
}

const mockUseUpstreamNodes = vi.fn<(...args: unknown[]) => { id: string; name: string; type: string }[]>()
vi.mock('./hooks/useUpstreamSteps', () => ({
  useUpstreamSteps: (...args: unknown[]) =>
    mockUseUpstreamNodes(...args) as { id: string; name: string; type: string }[],
}))

const mockActivities = vi.fn<() => { id: string; name: string; type: string }[] | undefined>()
const mockTriggers = vi.fn<() => { id: string; name: string; type: string }[] | undefined>()
vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: unknown) => unknown) =>
    selector({
      currentWorkflow: {
        workflow: { activities: mockActivities() ?? [] },
        triggers: mockTriggers() ?? [],
      },
    }),
}))

const mockPinInputMock = vi.fn()
const mockUnpinInputMock = vi.fn()
const mockUnpinAllInputMocks = vi.fn()
const mockHasInputMock = vi.fn<(nodeId: string, predecessorId: string) => boolean>()
const mockGetInputMockCount = vi.fn<(nodeId: string) => number>()
const mockGetInputMocks = vi.fn<(nodeId: string) => Record<string, unknown>>()
let mockPinnedData: Record<string, { outputMock?: Record<string, unknown>; inputMocks?: Record<string, unknown> }> = {}

vi.mock('../../../stores/useMockDataStore', () => ({
  useMockDataStore: Object.assign(
    (selector: (state: unknown) => unknown) =>
      selector({
        get pinInputMock() {
          return mockPinInputMock
        },
        get unpinInputMock() {
          return mockUnpinInputMock
        },
        get unpinAllInputMocks() {
          return mockUnpinAllInputMocks
        },
        get hasInputMock() {
          return mockHasInputMock
        },
        get getInputMockCount() {
          return mockGetInputMockCount
        },
        get getInputMocks() {
          return mockGetInputMocks
        },
        get pinnedData() {
          return mockPinnedData
        },
      }),
    {
      getState: () => ({
        get getInputMocks() {
          return mockGetInputMocks
        },
      }),
    }
  ),
}))

const upstreamNodes = [{ id: 'upstream-1', name: 'Previous Step', type: 'script' }]

const executionData = {
  'upstream-1': {
    timestamp: '2025-11-14T13:00:12.004-7:00',
    'Readable date': 'November 14th 2025, 8:17:40 AM',
    Year: 2025,
  },
}

describe('InputPanel', () => {
  beforeEach(() => {
    // Reset mock data store to a known state before each test
    mockGetInputMockCount.mockReturnValue(0)
    mockHasInputMock.mockReturnValue(false)
    mockGetInputMocks.mockImplementation(() => ({}))
    mockPinnedData = {}
  })
  it('shows "not connected" empty state when no upstream nodes exist', () => {
    mockUseUpstreamNodes.mockReturnValue([])

    render(<InputPanel nodeId="node-1" />)

    expect(screen.getByText('No input data')).toBeInTheDocument()
    expect(screen.getByText('Input data can only be displayed when a step is connected and run')).toBeInTheDocument()
  })

  it('shows schema preview when upstream node type has a known schema and no execution data', async () => {
    mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

    render(<InputPanel nodeId="node-1" />)

    await waitFor(
      () => {
        expect(screen.getByText('Expected output fields (run step to see actual values)')).toBeInTheDocument()
        expect(screen.getByRole('tree', { name: 'Schema preview' })).toBeInTheDocument()
        expect(screen.getByText('T stdout')).toBeInTheDocument()
        expect(screen.getByText('# return_code')).toBeInTheDocument()
      },
      { timeout: 15_000 }
    )
  }, 20_000)

  it('shows empty state when upstream node type has no known schema and no execution data', () => {
    mockUseUpstreamNodes.mockReturnValue([{ id: 'upstream-1', name: 'Unknown Step', type: 'unknown_type' }])

    render(<InputPanel nodeId="node-1" />)

    expect(screen.getByText('Input not available')).toBeInTheDocument()
    expect(screen.getByText('Run previous step to populate input')).toBeInTheDocument()
  })

  it('shows trigger input_schema fields as schema preview', () => {
    mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Manual Trigger', type: 'manual_trigger' }])
    mockTriggers.mockReturnValue([
      {
        id: 'real-trigger-id',
        name: 'Manual Trigger',
        type: 'manual_trigger',
        parameters: {
          input_schema: {
            type: 'object',
            properties: {
              hostname: { type: 'string', description: 'Target server' },
            },
          },
        },
      },
    ] as unknown as { id: string; name: string; type: string }[])

    render(<InputPanel nodeId="node-1" />)

    expect(screen.getByText('Expected output fields (run step to see actual values)')).toBeInTheDocument()
    expect(screen.getByText('T hostname')).toBeInTheDocument()
  })

  it('renders header with "Input" title', () => {
    mockUseUpstreamNodes.mockReturnValue([])

    render(<InputPanel nodeId="node-1" />)

    expect(screen.getByRole('heading', { name: 'Input' })).toBeInTheDocument()
  })

  it('passes the nodeId to useUpstreamSteps', () => {
    mockUseUpstreamNodes.mockReturnValue([])

    render(<InputPanel nodeId="test-node-42" />)

    expect(mockUseUpstreamNodes).toHaveBeenCalledWith('test-node-42')
  })

  it('renders Schema view by default when execution data exists', () => {
    mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

    render(<InputPanel nodeId="node-1" executionData={executionData} />)

    expect(screen.getByText('T timestamp')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Schema', pressed: true })).toBeInTheDocument()
  })

  it('switches to Table view when Table toggle clicked', async () => {
    const user = userEvent.setup()
    mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

    render(<InputPanel nodeId="node-1" executionData={executionData} />)

    await user.click(screen.getByRole('button', { name: 'Table' }))

    expect(screen.getByRole('button', { name: 'Table', pressed: true })).toBeInTheDocument()
  })

  it('switches to JSON view when JSON toggle clicked', async () => {
    const user = userEvent.setup()
    mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

    render(<InputPanel nodeId="node-1" executionData={executionData} />)

    await user.click(screen.getByRole('button', { name: 'JSON' }))

    expect(screen.getByRole('button', { name: 'JSON', pressed: true })).toBeInTheDocument()
  })

  it('renders collapsible Variables and context section', async () => {
    const user = userEvent.setup()
    mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

    render(<InputPanel nodeId="node-1" executionData={executionData} />)

    const toggle = screen.getByRole('button', { name: /Variables and context/i })
    expect(toggle).toBeInTheDocument()

    await user.click(toggle)

    expect(screen.getByText('{} workflow_context')).toBeInTheDocument()
    expect(screen.getByText('T now')).toBeInTheDocument()
  })

  it('shows type-label section headers when upstream activity names are empty', () => {
    mockUseUpstreamNodes.mockReturnValue([
      { id: 'up-1', name: '', type: 'converge' },
      { id: 'up-2', name: '   ', type: 'script' },
      { id: 'up-3', name: 'Custom Name', type: 'script' },
    ])

    render(<InputPanel nodeId="node-1" />)

    expect(screen.getByRole('button', { name: 'Converge' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Script' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Custom Name' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Variables and context/i })).toBeInTheDocument()
  })

  it('uses type labels in set mock data dropdown for unnamed upstream nodes', async () => {
    const user = userEvent.setup()
    mockUseUpstreamNodes.mockReturnValue([
      { id: 'up-1', name: '', type: 'converge' },
      { id: 'up-2', name: '', type: 'script' },
    ])

    render(<InputPanel nodeId="node-1" />)

    await user.click(screen.getByRole('button', { name: /Set mock data/i }))

    expect(screen.getByRole('menuitem', { name: 'Converge' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Script' })).toBeInTheDocument()
  })

  it('opens mock editor with type-label predecessor name for unnamed upstream', async () => {
    const user = userEvent.setup()
    mockUseUpstreamNodes.mockReturnValue([{ id: 'up-1', name: '', type: 'http_request' }])

    renderWithProvider(<InputPanel nodeId="node-1" />)

    await user.click(screen.getByRole('button', { name: /Set mock data/i }))
    await user.click(screen.getByRole('menuitem', { name: 'REST API' }))

    expect(screen.getByText(/Editing mock data for: REST API/i)).toBeInTheDocument()
  })

  it('falls back to predecessor id in mock editor when upstream node disappears', async () => {
    const user = userEvent.setup()
    mockUseUpstreamNodes.mockReturnValue([{ id: 'up-1', name: '', type: 'http_request' }])

    const { rerender } = renderWithProvider(<InputPanel nodeId="node-1" />)

    await user.click(screen.getByRole('button', { name: /Set mock data/i }))
    await user.click(screen.getByRole('menuitem', { name: 'REST API' }))
    expect(screen.getByText(/Editing mock data for: REST API/i)).toBeInTheDocument()

    mockUseUpstreamNodes.mockReturnValue([])
    rerender(
      <ColorSchemeProvider>
        <InputPanel nodeId="node-1" />
      </ColorSchemeProvider>
    )

    expect(screen.getByText(/Editing mock data for: up-1/i)).toBeInTheDocument()
  })

  it('shows schema preview via sourceNodeId fallback when no edges exist', () => {
    mockUseUpstreamNodes.mockReturnValue([])
    mockActivities.mockReturnValue([{ id: 'source-1', name: 'Fetch Data', type: 'script' }])

    render(<InputPanel nodeId="" sourceNodeId="source-1" />)

    expect(screen.getByText('Expected output fields (run step to see actual values)')).toBeInTheDocument()
    expect(screen.getByText('T stdout')).toBeInTheDocument()
    expect(screen.getByText('# return_code')).toBeInTheDocument()
  })

  describe('chain deletion and reconnection with execution data', () => {
    // 6-node chain: trigger → A → B → C → D → E
    // All are script nodes so they have known output schemas
    const fullChain = [
      { id: 'node-a', name: 'Step A', type: 'script' },
      { id: 'node-b', name: 'Step B', type: 'script' },
      { id: 'node-c', name: 'Step C', type: 'script' },
      { id: 'node-d', name: 'Step D', type: 'script' },
      { id: 'node-e', name: 'Step E', type: 'script' },
      { id: 'trigger-1', name: 'Trigger', type: 'manual_trigger' },
    ]

    const chainExecutionData = {
      'trigger-1': { timestamp: '2025-01-01T00:00:00Z' },
      'node-a': { stdout: 'output-a', return_code: 0 },
      'node-b': { stdout: 'output-b', return_code: 0 },
      'node-c': { stdout: 'output-c', return_code: 0 },
      'node-d': { stdout: 'output-d', return_code: 0 },
    }

    it('shows execution data from direct predecessor in a full chain', () => {
      mockUseUpstreamNodes.mockReturnValue(fullChain)

      render(<InputPanel nodeId="node-e" executionData={chainExecutionData} />)

      // Default selected node is the first upstream (node-a) — shows its real data
      expect(screen.getByRole('button', { name: 'Schema', pressed: true })).toBeInTheDocument()
      expect(screen.getByText('output-a')).toBeInTheDocument()
    })

    it('shows node selector dropdown when multiple upstream nodes exist', () => {
      mockUseUpstreamNodes.mockReturnValue(fullChain)

      render(<InputPanel nodeId="node-e" executionData={chainExecutionData} />)

      // Dropdown should appear because there are 6 upstream nodes
      expect(screen.getByRole('button', { name: 'Step A' })).toBeInTheDocument()
    })

    it('can switch between upstream nodes to view different execution data', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(fullChain)

      render(<InputPanel nodeId="node-e" executionData={chainExecutionData} />)

      // First upstream node (Step A) is expanded by default and shows its data
      expect(screen.getByText('output-a')).toBeInTheDocument()

      // Expand Step D section to see its data
      await user.click(screen.getByRole('button', { name: 'Step D' }))

      // Now shows Step D's data alongside Step A's
      expect(screen.getByText('output-d')).toBeInTheDocument()
    })

    it('after deleting a middle node, downstream only sees remaining connected ancestors', () => {
      // Delete node-c: node-e now only sees node-d (isolated after the break)
      const brokenChain = [{ id: 'node-d', name: 'Step D', type: 'script' }]
      mockUseUpstreamNodes.mockReturnValue(brokenChain)

      const brokenExecutionData = {
        'node-d': { stdout: 'output-d', return_code: 0 },
      }

      render(<InputPanel nodeId="node-e" executionData={brokenExecutionData} />)

      // Shows node-d's data, no dropdown (only 1 upstream)
      expect(screen.getByText('output-d')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Step A' })).not.toBeInTheDocument()
    })

    it('after deleting a middle node, the pre-break chain remains intact', () => {
      // node-b still sees node-a and trigger (unaffected by the break after node-c)
      const preBreakChain = [
        { id: 'node-a', name: 'Step A', type: 'script' },
        { id: 'trigger-1', name: 'Trigger', type: 'manual_trigger' },
      ]
      mockUseUpstreamNodes.mockReturnValue(preBreakChain)

      const preBreakExecutionData = {
        'node-a': { stdout: 'output-a', return_code: 0 },
        'trigger-1': { timestamp: '2025-01-01T00:00:00Z' },
      }

      render(<InputPanel nodeId="node-b" executionData={preBreakExecutionData} />)

      // Shows node-a's data, dropdown available to switch to trigger
      expect(screen.getByText('output-a')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Step A' })).toBeInTheDocument()
    })

    it('after reconnecting the chains, full ancestor data is available again', async () => {
      const user = userEvent.setup()
      // Reconnect: node-b → node-d (skipping deleted node-c)
      const reconnectedChain = [
        { id: 'node-d', name: 'Step D', type: 'script' },
        { id: 'node-b', name: 'Step B', type: 'script' },
        { id: 'node-a', name: 'Step A', type: 'script' },
        { id: 'trigger-1', name: 'Trigger', type: 'manual_trigger' },
      ]
      mockUseUpstreamNodes.mockReturnValue(reconnectedChain)

      const reconnectedExecutionData = {
        'node-d': { stdout: 'output-d', return_code: 0 },
        'node-b': { stdout: 'output-b', return_code: 0 },
        'node-a': { stdout: 'output-a', return_code: 0 },
        'trigger-1': { timestamp: '2025-01-01T00:00:00Z' },
      }

      render(<InputPanel nodeId="node-e" executionData={reconnectedExecutionData} />)

      // First upstream (node-d) is expanded by default
      expect(screen.getByText('output-d')).toBeInTheDocument()

      // Expand Step A section
      await user.click(screen.getByRole('button', { name: 'Step A' }))
      expect(screen.getByText('output-a')).toBeInTheDocument()

      // Expand Step B section
      await user.click(screen.getByRole('button', { name: 'Step B' }))
      expect(screen.getByText('output-b')).toBeInTheDocument()
    })

    it('schema preview reflects broken chain when no execution data exists', () => {
      // Same broken chain scenario but without execution data (design-time)
      const brokenChain = [{ id: 'node-d', name: 'Step D', type: 'script' }]
      mockUseUpstreamNodes.mockReturnValue(brokenChain)

      render(<InputPanel nodeId="node-e" />)

      // Shows schema preview for script node (Step D), no dropdown
      expect(screen.getByText('Expected output fields (run step to see actual values)')).toBeInTheDocument()
      expect(screen.getByText('T stdout')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Step A' })).not.toBeInTheDocument()
    })

    it('schema preview shows all ancestors after reconnection without execution data', () => {
      // Reconnected chain, design-time (no execution data)
      const reconnectedChain = [
        { id: 'node-d', name: 'Step D', type: 'script' },
        { id: 'node-b', name: 'Step B', type: 'script' },
        { id: 'node-a', name: 'Step A', type: 'script' },
        { id: 'trigger-1', name: 'Trigger', type: 'manual_trigger' },
      ]
      mockUseUpstreamNodes.mockReturnValue(reconnectedChain)

      render(<InputPanel nodeId="node-e" />)

      // All ancestors visible as expandable sections with schema previews
      expect(screen.getAllByText('Expected output fields (run step to see actual values)').length).toBeGreaterThan(0)
      expect(screen.getByRole('button', { name: 'Step D' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Step B' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Step A' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Trigger' })).toBeInTheDocument()
    })
  })

  it('has no accessibility violations when not connected', async () => {
    mockUseUpstreamNodes.mockReturnValue([])

    const { container } = render(<InputPanel nodeId="node-1" />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when connected but not run', async () => {
    mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

    const { container } = render(<InputPanel nodeId="node-1" />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  describe('Mock data flow', () => {
    beforeEach(() => {
      mockGetInputMockCount.mockReturnValue(0)
      mockHasInputMock.mockReturnValue(false)
      // Always return an object, even if empty
      mockGetInputMocks.mockImplementation(() => ({}))
      mockPinnedData = {}
      vi.clearAllMocks()
    })

    it('opens mock editor when "Set mock data" dropdown item is clicked', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      renderWithProvider(<InputPanel nodeId="node-1" />)

      // Open the "Set mock data" dropdown
      await user.click(screen.getByRole('button', { name: /Set mock data/i }))

      // Click the predecessor node in the dropdown
      await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

      // Verify mock editor is now open
      expect(screen.getByText(/Editing mock data for:/i)).toBeInTheDocument()
      expect(screen.getByTestId('inline-code-editor')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Pin data' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('cancels mock editor without pinning when Cancel is clicked', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      renderWithProvider(<InputPanel nodeId="node-1" />)

      // Open mock editor
      await user.click(screen.getByRole('button', { name: /Set mock data/i }))
      await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

      // Verify editor is open
      expect(screen.getByText(/Editing mock data for:/i)).toBeInTheDocument()

      // Click Cancel
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      // Verify editor is closed and no pinning occurred
      expect(screen.queryByText(/Editing mock data for:/i)).not.toBeInTheDocument()
      expect(mockPinInputMock).not.toHaveBeenCalled()
      expect(screen.getByRole('heading', { name: 'Input' })).toBeInTheDocument()
    })

    it('shows pin and cancel buttons in mock editor', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      renderWithProvider(<InputPanel nodeId="node-1" />)

      // Open mock editor
      await user.click(screen.getByRole('button', { name: /Set mock data/i }))
      await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

      // Verify editor UI
      expect(screen.getByTestId('inline-code-editor')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Pin data' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('displays "Mock data pinned" badge when mocks exist', () => {
      mockGetInputMockCount.mockReturnValue(2)
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('Mock data pinned (2)')).toBeInTheDocument()
    })

    it('shows "Unpin data" dropdown when mocks exist', async () => {
      const user = userEvent.setup()
      mockGetInputMockCount.mockReturnValue(1)
      mockHasInputMock.mockReturnValue(true)
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" />)

      // Get all Unpin data buttons (dropdown MenuToggle in header)
      const unpinButtons = screen.getAllByRole('button', { name: /Unpin data/i })
      // The dropdown toggle in the header is the first one (if not expanded)
      const unpinDropdownToggle = unpinButtons[0]
      expect(unpinDropdownToggle).toBeInTheDocument()

      // Open the dropdown
      await user.click(unpinDropdownToggle)

      // Should show individual node and "Unpin all"
      expect(screen.getByRole('menuitem', { name: 'Previous Step' })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: 'Unpin all' })).toBeInTheDocument()
    })

    it('unpins single predecessor when clicked in Unpin dropdown', async () => {
      const user = userEvent.setup()
      mockGetInputMockCount.mockReturnValue(1)
      mockHasInputMock.mockReturnValue(true)
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" />)

      // Open Unpin dropdown - get all and use the first one (dropdown toggle)
      const unpinButtons = screen.getAllByRole('button', { name: /Unpin data/i })
      await user.click(unpinButtons[0])

      // Click on the predecessor
      await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

      // Verify unpinInputMock was called
      expect(mockUnpinInputMock).toHaveBeenCalledWith('node-1', 'upstream-1')
    })

    it('unpins all when "Unpin all" is clicked', async () => {
      const user = userEvent.setup()
      mockGetInputMockCount.mockReturnValue(2)
      mockHasInputMock.mockReturnValue(true)
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" />)

      // Open Unpin dropdown
      const unpinButtons = screen.getAllByRole('button', { name: /Unpin data/i })
      await user.click(unpinButtons[0])

      // Click "Unpin all"
      await user.click(screen.getByRole('menuitem', { name: 'Unpin all' }))

      // Verify unpinAllInputMocks was called
      expect(mockUnpinAllInputMocks).toHaveBeenCalledWith('node-1')
    })

    it('shows individual "Unpin data" button per predecessor when mock is pinned', async () => {
      const user = userEvent.setup()
      mockGetInputMockCount.mockReturnValue(1)
      mockHasInputMock.mockImplementation((_nodeId: string, predId: string) => predId === 'upstream-1')
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" />)

      // Expand the first upstream section
      const sectionToggle = screen.getByRole('button', { name: 'Previous Step' })
      await user.click(sectionToggle)

      // Should show "Mock data pinned" label and "Unpin data" button
      expect(screen.getByText('Mock data pinned')).toBeInTheDocument()
      const unpinButtons = screen.getAllByRole('button', { name: /Unpin data/i })
      // Should have both the dropdown toggle and the inline button
      expect(unpinButtons.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Search filtering', () => {
    it('does not show search input when no data exists', () => {
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" />)

      expect(screen.queryByPlaceholderText('Search fields')).not.toBeInTheDocument()
    })

    it('shows search input when execution data exists', () => {
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" executionData={executionData} />)

      expect(screen.getByPlaceholderText('Search fields')).toBeInTheDocument()
    })

    it('updates search term when user types in search input', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" executionData={executionData} />)

      const searchInput = screen.getByPlaceholderText('Search fields')
      await user.type(searchInput, 'timestamp')

      expect(searchInput).toHaveValue('timestamp')
    })

    it('clears search term when clear button is clicked', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" executionData={executionData} />)

      const searchInput = screen.getByPlaceholderText('Search fields')
      await user.type(searchInput, 'test')
      expect(searchInput).toHaveValue('test')

      // Find and click the reset button in the SearchInput
      const resetButton = screen.getByRole('button', { name: /reset/i })
      await user.click(resetButton)

      expect(searchInput).toHaveValue('')
    })
  })

  describe('Info alert with "Run previous steps"', () => {
    it('shows info alert with "Run previous steps" button when props provided and no data', () => {
      const mockOnRunPreviousSteps = vi.fn()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" workflowId="workflow-123" onRunPreviousSteps={mockOnRunPreviousSteps} />)

      // Should show the alert
      expect(screen.getByText('Expected input fields')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Run previous steps' })).toBeInTheDocument()
    })

    it('calls onRunPreviousSteps when "Run previous steps" button is clicked', async () => {
      const user = userEvent.setup()
      const mockOnRunPreviousSteps = vi.fn()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" workflowId="workflow-123" onRunPreviousSteps={mockOnRunPreviousSteps} />)

      await user.click(screen.getByRole('button', { name: 'Run previous steps' }))

      expect(mockOnRunPreviousSteps).toHaveBeenCalledTimes(1)
    })

    it('does not show info alert when execution data exists', () => {
      const mockOnRunPreviousSteps = vi.fn()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(
        <InputPanel
          nodeId="node-1"
          executionData={executionData}
          workflowId="workflow-123"
          onRunPreviousSteps={mockOnRunPreviousSteps}
        />
      )

      // Alert should not appear when data exists
      expect(screen.queryByText('Expected input fields')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Run previous steps' })).not.toBeInTheDocument()
    })

    it('does not show info alert when onRunPreviousSteps is not provided', () => {
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" workflowId="workflow-123" />)

      expect(screen.queryByText('Expected input fields')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Run previous steps' })).not.toBeInTheDocument()
    })

    it('does not show info alert when workflowId is not provided', () => {
      const mockOnRunPreviousSteps = vi.fn()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" onRunPreviousSteps={mockOnRunPreviousSteps} />)

      expect(screen.queryByText('Expected input fields')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Run previous steps' })).not.toBeInTheDocument()
    })
  })

  describe('Pinned mock data in Schema view', () => {
    it('renders schema view with pinned mock values', () => {
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)
      mockGetInputMockCount.mockReturnValue(1)
      mockHasInputMock.mockReturnValue(true)
      mockPinnedData = {
        'node-1': {
          inputMocks: {
            'upstream-1': { hostname: 'mock-server', port: 8080 },
          },
        },
      }

      render(<InputPanel nodeId="node-1" />)

      // Pinned mock data should appear in Schema view
      expect(screen.getByText('mock-server')).toBeInTheDocument()
      expect(screen.getByText('8080')).toBeInTheDocument()
    })
  })

  describe('Type mapping (mapJsonSchemaType)', () => {
    it('maps string type to string', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {
            input_schema: {
              type: 'object',
              properties: { field1: { type: 'string' } },
            },
          },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('T field1')).toBeInTheDocument()
    })

    it('maps number type to number', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {
            input_schema: {
              type: 'object',
              properties: { count: { type: 'number' } },
            },
          },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('# count')).toBeInTheDocument()
    })

    it('maps integer type to number', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {
            input_schema: {
              type: 'object',
              properties: { count: { type: 'integer' } },
            },
          },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('# count')).toBeInTheDocument()
    })

    it('maps boolean type to boolean', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {
            input_schema: {
              type: 'object',
              properties: { enabled: { type: 'boolean' } },
            },
          },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('✓ enabled')).toBeInTheDocument()
    })

    it('maps object type to object', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {
            input_schema: {
              type: 'object',
              properties: { config: { type: 'object' } },
            },
          },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('{} config')).toBeInTheDocument()
    })

    it('maps array type to array', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {
            input_schema: {
              type: 'object',
              properties: { items: { type: 'array' } },
            },
          },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('[] items')).toBeInTheDocument()
    })

    it('maps unknown type to unknown', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {
            input_schema: {
              type: 'object',
              properties: { field: { type: 'custom_type' } },
            },
          },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('? field')).toBeInTheDocument()
    })

    it('maps undefined type to unknown', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {
            input_schema: {
              type: 'object',
              properties: { field: {} },
            },
          },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('? field')).toBeInTheDocument()
    })
  })

  describe('getTriggerInputSchemaFields', () => {
    it('shows no-trigger-schema empty state when trigger has no input_schema', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {},
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('No schema defined')).toBeInTheDocument()
    })

    it('shows no-trigger-schema empty state when input_schema is not an object', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: { input_schema: 'not-an-object' },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('No schema defined')).toBeInTheDocument()
    })

    it('shows no-trigger-schema empty state when input_schema has no properties', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: { input_schema: { type: 'object' } },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('No schema defined')).toBeInTheDocument()
    })

    it('shows no-trigger-schema empty state when input_schema has empty properties', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'trigger-0',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {
            input_schema: {
              type: 'object',
              properties: {},
            },
          },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('No schema defined')).toBeInTheDocument()
    })

    it('uses trigger ID from index when parseTriggerIndex returns a valid index', () => {
      mockUseUpstreamNodes.mockReturnValue([{ id: 'trigger-0', name: 'Trigger', type: 'manual_trigger' }])
      mockTriggers.mockReturnValue([
        {
          id: 'real-trigger-id',
          name: 'Trigger',
          type: 'manual_trigger',
          parameters: {
            input_schema: {
              type: 'object',
              properties: { field: { type: 'string' } },
            },
          },
        },
      ] as unknown as { id: string; name: string; type: string }[])

      render(<InputPanel nodeId="node-1" />)

      expect(screen.getByText('T field')).toBeInTheDocument()
    })
  })

  describe('effectiveUpstream fallback to sourceNodeId', () => {
    it('includes source trigger in effectiveUpstream when no upstream edges exist', () => {
      mockUseUpstreamNodes.mockReturnValue([])
      mockTriggers.mockReturnValue([{ id: 'source-trigger', name: 'Source Trigger', type: 'manual_trigger' }])

      render(<InputPanel nodeId="" sourceNodeId="source-trigger" />)

      // The source trigger should appear in the expandable section
      expect(screen.getByRole('button', { name: 'Source Trigger' })).toBeInTheDocument()
    })

    it('resolves trigger display ID (trigger-0) to real trigger in effectiveUpstream', () => {
      mockUseUpstreamNodes.mockReturnValue([])
      mockTriggers.mockReturnValue([{ id: 'trigger_webhook_0', name: 'Webhook Trigger', type: 'webhook_trigger' }])

      render(<InputPanel nodeId="" sourceNodeId="trigger-0" />)

      expect(screen.getByRole('button', { name: 'Webhook Trigger' })).toBeInTheDocument()
    })

    it('returns empty effectiveUpstream when sourceNodeId does not match any activity or trigger', () => {
      mockUseUpstreamNodes.mockReturnValue([])
      mockActivities.mockReturnValue([])
      mockTriggers.mockReturnValue([])

      render(<InputPanel nodeId="" sourceNodeId="non-existent" />)

      expect(screen.getByText('No input data')).toBeInTheDocument()
    })
  })

  describe('Mock editor', () => {
    it('opens editor when setting mock data for a node with existing pinned data', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)
      mockGetInputMocks.mockReturnValue({ 'upstream-1': { field1: 'existing-value' } })

      renderWithProvider(<InputPanel nodeId="node-1" />)

      await user.click(screen.getByRole('button', { name: /Set mock data/i }))
      await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

      // Editor should be open with Pin and Cancel buttons
      expect(screen.getByRole('button', { name: 'Pin data' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('pre-fills mock editor with execution data when no pinned input mock exists', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)
      mockGetInputMocks.mockReturnValue({})

      renderWithProvider(<InputPanel nodeId="node-1" executionData={executionData} />)

      await user.click(screen.getByRole('button', { name: /Set mock data/i }))
      await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

      // Pin data to verify the editor was pre-filled with execution data (not a skeleton)
      await user.click(screen.getByRole('button', { name: 'Pin data' }))
      expect(mockPinInputMock).toHaveBeenCalledWith('node-1', 'upstream-1', executionData['upstream-1'])
    })

    it('pre-fills mock editor with upstream output mock when no execution data or input mock exists', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)
      mockGetInputMocks.mockReturnValue({})
      mockPinnedData = {
        'upstream-1': {
          outputMock: { mocked_stdout: 'from-output-pin', return_code: 0 },
        },
      }

      renderWithProvider(<InputPanel nodeId="node-1" />)

      await user.click(screen.getByRole('button', { name: /Set mock data/i }))
      await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

      await user.click(screen.getByRole('button', { name: 'Pin data' }))
      expect(mockPinInputMock).toHaveBeenCalledWith('node-1', 'upstream-1', {
        mocked_stdout: 'from-output-pin',
        return_code: 0,
      })
    })

    it('prefers execution data over upstream output mock for same predecessor', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)
      mockGetInputMocks.mockReturnValue({})
      mockPinnedData = {
        'upstream-1': {
          outputMock: { mocked_stdout: 'should-not-appear' },
        },
      }

      renderWithProvider(<InputPanel nodeId="node-1" executionData={executionData} />)

      await user.click(screen.getByRole('button', { name: /Set mock data/i }))
      await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

      await user.click(screen.getByRole('button', { name: 'Pin data' }))
      expect(mockPinInputMock).toHaveBeenCalledWith('node-1', 'upstream-1', executionData['upstream-1'])
    })

    it('prefers existing pinned input mock over execution data in mock editor', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)
      mockPinnedData = {
        'node-1': {
          inputMocks: { 'upstream-1': { custom_field: 'user-edited-value' } },
        },
      }

      renderWithProvider(<InputPanel nodeId="node-1" executionData={executionData} />)

      await user.click(screen.getByRole('button', { name: /Set mock data/i }))
      await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

      await user.click(screen.getByRole('button', { name: 'Pin data' }))
      expect(mockPinInputMock).toHaveBeenCalledWith('node-1', 'upstream-1', { custom_field: 'user-edited-value' })
    })
  })

  describe('Pinned output mock from upstream nodes', () => {
    it('merges upstream outputMock into execution data when present', () => {
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)
      mockPinnedData = {
        'upstream-1': {
          outputMock: { mocked_field: 'mocked_value' },
        },
      }

      render(<InputPanel nodeId="node-1" />)

      // Should display the pinned output mock as input
      expect(screen.getByText('mocked_value')).toBeInTheDocument()
    })
  })

  describe('Unpin single predecessor inline button', () => {
    it('shows inline unpin button when mock is pinned for a predecessor', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)
      mockGetInputMockCount.mockReturnValue(1)
      mockHasInputMock.mockImplementation((_nodeId: string, predId: string) => predId === 'upstream-1')

      render(<InputPanel nodeId="node-1" />)

      // Expand the section
      await user.click(screen.getByRole('button', { name: 'Previous Step' }))

      // Should show "Mock data pinned" label
      expect(screen.getByText('Mock data pinned')).toBeInTheDocument()

      // Should show the inline Unpin data button (the one visible in the expanded section)
      // Note: there are also buttons in the header dropdown, but when we expand a section
      // we see the inline button with the icon
      const unpinButtons = screen.getAllByRole('button', { name: /Unpin data/i })
      expect(unpinButtons.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('has no accessibility violations with mock data controls', async () => {
    mockGetInputMockCount.mockReturnValue(1)
    mockHasInputMock.mockReturnValue(true)
    mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

    const { container } = render(<InputPanel nodeId="node-1" executionData={executionData} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations in mock editor view', async () => {
    const user = userEvent.setup()
    mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

    const { container } = renderWithProvider(<InputPanel nodeId="node-1" />)

    // Open mock editor
    await user.click(screen.getByRole('button', { name: /Set mock data/i }))
    await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  describe('edge cases and mock data flows', () => {
    it('Unpin dropdown only shows predecessors that have input mocks', async () => {
      const user = userEvent.setup()
      const multipleUpstream = [
        { id: 'upstream-1', name: 'Step 1', type: 'script' },
        { id: 'upstream-2', name: 'Step 2', type: 'script' },
        { id: 'upstream-3', name: 'Step 3', type: 'script' },
      ]
      mockUseUpstreamNodes.mockReturnValue(multipleUpstream)
      mockGetInputMockCount.mockReturnValue(2)
      // Only upstream-1 and upstream-3 have mocks
      mockHasInputMock.mockImplementation(
        (_nodeId: string, predId: string) => predId === 'upstream-1' || predId === 'upstream-3'
      )

      render(<InputPanel nodeId="node-1" />)

      // Open Unpin dropdown
      const unpinButtons = screen.getAllByRole('button', { name: /Unpin data/i })
      await user.click(unpinButtons[0])

      // Should show only Step 1 and Step 3 (not Step 2)
      expect(screen.getByRole('menuitem', { name: 'Step 1' })).toBeInTheDocument()
      expect(screen.queryByRole('menuitem', { name: 'Step 2' })).not.toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: 'Step 3' })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: 'Unpin all' })).toBeInTheDocument()
    })

    it('ExpandableSection collapses when already expanded', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" executionData={executionData} />)

      // First upstream section is expanded by default
      const sectionToggle = screen.getByRole('button', { name: 'Previous Step' })
      expect(sectionToggle).toHaveAttribute('aria-expanded', 'true')

      // Click to collapse
      await user.click(sectionToggle)

      // Should now be collapsed
      expect(sectionToggle).toHaveAttribute('aria-expanded', 'false')
    })

    it('handleUnpinSingle closes dropdown after unpinning', async () => {
      const user = userEvent.setup()
      mockGetInputMockCount.mockReturnValue(1)
      mockHasInputMock.mockReturnValue(true)
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" />)

      // Open Unpin dropdown
      const unpinButtons = screen.getAllByRole('button', { name: /Unpin data/i })
      await user.click(unpinButtons[0])

      // Dropdown should be open with menuitem
      expect(screen.getByRole('menuitem', { name: 'Previous Step' })).toBeInTheDocument()

      // Click on the predecessor to unpin
      await user.click(screen.getByRole('menuitem', { name: 'Previous Step' }))

      // Verify unpinInputMock was called
      expect(mockUnpinInputMock).toHaveBeenCalledWith('node-1', 'upstream-1')

      // Dropdown should close (menuitem no longer visible)
      await waitFor(() => {
        expect(screen.queryByRole('menuitem', { name: 'Previous Step' })).not.toBeInTheDocument()
      })
    })

    it('Badge disappears after unpinAllInputMocks', async () => {
      const user = userEvent.setup()
      mockGetInputMockCount.mockReturnValue(2)
      mockHasInputMock.mockReturnValue(true)
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      const { rerender } = render(<InputPanel nodeId="node-1" />)

      // Badge should be visible
      expect(screen.getByText('Mock data pinned (2)')).toBeInTheDocument()

      // Click "Unpin all"
      const unpinButtons = screen.getAllByRole('button', { name: /Unpin data/i })
      await user.click(unpinButtons[0])
      await user.click(screen.getByRole('menuitem', { name: 'Unpin all' }))

      // Simulate store update after unpinAll
      mockGetInputMockCount.mockReturnValue(0)
      mockHasInputMock.mockReturnValue(false)

      // Re-render with updated mock state
      rerender(<InputPanel nodeId="node-1" />)

      // Badge should no longer be visible
      expect(screen.queryByText(/Mock data pinned/i)).not.toBeInTheDocument()
    })

    it('Multiple predecessor mock editing updates editingPredecessorId correctly', async () => {
      const user = userEvent.setup()
      const multipleUpstream = [
        { id: 'upstream-1', name: 'Step 1', type: 'script' },
        { id: 'upstream-2', name: 'Step 2', type: 'script' },
      ]
      mockUseUpstreamNodes.mockReturnValue(multipleUpstream)

      renderWithProvider(<InputPanel nodeId="node-1" />)

      // Open "Set mock data" dropdown
      await user.click(screen.getByRole('button', { name: /Set mock data/i }))

      // Click Step 1
      await user.click(screen.getByRole('menuitem', { name: 'Step 1' }))

      // Editor should open for Step 1
      expect(screen.getByText(/Editing mock data for: Step 1/i)).toBeInTheDocument()

      // Cancel
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      // Open "Set mock data" dropdown again
      await user.click(screen.getByRole('button', { name: /Set mock data/i }))

      // Click Step 2
      await user.click(screen.getByRole('menuitem', { name: 'Step 2' }))

      // Editor should now show Step 2
      expect(screen.getByText(/Editing mock data for: Step 2/i)).toBeInTheDocument()
    })

    it('effectiveUpstream includes source trigger when upstreamNodes is empty', () => {
      mockUseUpstreamNodes.mockReturnValue([])
      mockTriggers.mockReturnValue([{ id: 'source-trigger', name: 'Source Trigger', type: 'manual_trigger' }])

      render(<InputPanel nodeId="" sourceNodeId="source-trigger" />)

      // The source trigger should appear in the upstream list
      expect(screen.getByRole('button', { name: 'Source Trigger' })).toBeInTheDocument()
    })

    it('Search term persists across view switches', async () => {
      const user = userEvent.setup()
      mockUseUpstreamNodes.mockReturnValue(upstreamNodes)

      render(<InputPanel nodeId="node-1" executionData={executionData} />)

      const searchInput = screen.getByPlaceholderText('Search fields')

      // Enter search term
      await user.type(searchInput, 'timestamp')
      expect(searchInput).toHaveValue('timestamp')

      // Switch to Table view
      await user.click(screen.getByRole('button', { name: 'Table' }))

      // Search term should still be there
      expect(searchInput).toHaveValue('timestamp')

      // Switch to JSON view
      await user.click(screen.getByRole('button', { name: 'JSON' }))

      // Search term should still be there
      expect(searchInput).toHaveValue('timestamp')

      // Switch back to Schema
      await user.click(screen.getByRole('button', { name: 'Schema' }))

      // Search term should still be there
      expect(searchInput).toHaveValue('timestamp')
    })
  })
})
