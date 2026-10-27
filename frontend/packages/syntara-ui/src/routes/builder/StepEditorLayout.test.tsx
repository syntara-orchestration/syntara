import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { AdjacentSteps } from './panels/hooks/useAdjacentSteps'
import { StepEditorLayout } from './StepEditorLayout'

vi.mock('./panels/InputPanel', () => ({
  InputPanel: ({
    nodeId,
    executionData,
    sourceNodeId,
  }: {
    nodeId: string
    executionData?: unknown
    sourceNodeId?: string | null
  }) => (
    <div data-testid="input-panel">
      Input for {nodeId}
      {executionData ? <span data-testid="input-has-data">has data</span> : null}
      {sourceNodeId ? <span data-testid="input-source-node">{sourceNodeId}</span> : null}
    </div>
  ),
}))

vi.mock('./panels/OutputPanel', () => ({
  OutputPanel: ({ outputData }: { outputData?: unknown }) => (
    <div data-testid="output-panel">{outputData ? <span data-testid="output-has-data">has data</span> : null}</div>
  ),
}))

const mockUseStepExecutionData = vi.fn()

vi.mock('./panels/hooks/useStepExecutionData', () => ({
  useStepExecutionData: (...args: unknown[]): { inputData: null; outputData: null; isLoading: boolean } =>
    mockUseStepExecutionData(...args) as { inputData: null; outputData: null; isLoading: boolean },
}))

const mockUseAdjacentSteps = vi.fn<(nodeId?: string) => AdjacentSteps>()

vi.mock('./panels/hooks/useAdjacentSteps', () => ({
  useAdjacentSteps: (nodeId?: string) => mockUseAdjacentSteps(nodeId),
}))

vi.mock('./panels/StepPanelNavigationArrow', () => ({
  StepPanelNavigationArrow: ({
    direction,
    steps,
    onNavigate,
  }: {
    direction: string
    steps: { id: string; name?: string }[]
    onNavigate: (id: string) => void
  }) =>
    steps.length > 0 ? (
      <button type="button" data-testid={`nav-arrow-${direction}`} onClick={() => onNavigate(steps[0]?.id ?? '')}>
        {direction}
      </button>
    ) : null,
}))

vi.mock('../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({ showInfo: vi.fn() })),
}))

describe('StepEditorLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseStepExecutionData.mockReturnValue({
      inputData: null,
      outputData: null,
      isLoading: false,
    })
    mockUseAdjacentSteps.mockReturnValue({ upstream: [], downstream: [] })
  })

  it('renders InputPanel in left column when showInputPanel is true and nodeId is provided', () => {
    render(<StepEditorLayout parametersContent={<div>Parameters</div>} showInputPanel={true} nodeId="node-42" />)

    const inputPanel = screen.getByTestId('input-panel')
    expect(inputPanel).toBeInTheDocument()
    expect(inputPanel).toHaveTextContent('Input for node-42')
  })

  it('does not render InputPanel when showInputPanel is false', () => {
    render(<StepEditorLayout parametersContent={<div>Parameters</div>} showInputPanel={false} nodeId="node-42" />)

    expect(screen.queryByTestId('input-panel')).not.toBeInTheDocument()
  })

  it('renders parameters content in center column', () => {
    render(<StepEditorLayout parametersContent={<div>My Parameters Content</div>} showInputPanel={false} />)

    expect(screen.getByText('My Parameters Content')).toBeInTheDocument()
  })

  it('renders OutputPanel in right column', () => {
    render(<StepEditorLayout parametersContent={<div>Parameters</div>} showInputPanel={false} />)

    expect(screen.getByTestId('output-panel')).toBeInTheDocument()
  })

  it('passes executionId to useStepExecutionData hook', () => {
    render(
      <StepEditorLayout
        parametersContent={<div>Parameters</div>}
        showInputPanel={false}
        nodeId="node-1"
        executionId="exec-99"
      />
    )

    expect(mockUseStepExecutionData).toHaveBeenCalledWith('node-1', 'exec-99', undefined)
  })

  it('passes empty string nodeId to hook when nodeId is not provided', () => {
    render(<StepEditorLayout parametersContent={<div>Parameters</div>} showInputPanel={false} executionId="exec-99" />)

    expect(mockUseStepExecutionData).toHaveBeenCalledWith('', 'exec-99', undefined)
  })

  it('passes executionData from hook to InputPanel', () => {
    mockUseStepExecutionData.mockReturnValue({
      inputData: { 'upstream-1': { value: 'test' } },
      outputData: null,
      isLoading: false,
    })

    render(
      <StepEditorLayout
        parametersContent={<div>Parameters</div>}
        showInputPanel={true}
        nodeId="node-1"
        executionId="exec-1"
      />
    )

    expect(screen.getByTestId('input-has-data')).toBeInTheDocument()
  })

  it('passes outputData from hook to OutputPanel', () => {
    mockUseStepExecutionData.mockReturnValue({
      inputData: null,
      outputData: { result: 'hello' },
      isLoading: false,
    })

    render(
      <StepEditorLayout
        parametersContent={<div>Parameters</div>}
        showInputPanel={false}
        nodeId="node-1"
        executionId="exec-1"
      />
    )

    expect(screen.getByTestId('output-has-data')).toBeInTheDocument()
  })

  it('passes sourceNodeId to InputPanel when provided', () => {
    render(
      <StepEditorLayout
        parametersContent={<div>Parameters</div>}
        showInputPanel={true}
        nodeId="node-1"
        sourceNodeId="source-1"
      />
    )

    const sourceNode = screen.getByTestId('input-source-node')
    expect(sourceNode).toHaveTextContent('source-1')
  })

  it('does not render sourceNodeId indicator when not provided', () => {
    render(<StepEditorLayout parametersContent={<div>Parameters</div>} showInputPanel={true} nodeId="node-1" />)

    expect(screen.queryByTestId('input-source-node')).not.toBeInTheDocument()
  })

  describe('Update button (edit mode)', () => {
    it('calls form submit when Update button is clicked with formId in edit mode', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(
        <>
          <form id="test-form" data-testid="test-form">
            <input type="text" />
          </form>
          <StepEditorLayout
            parametersContent={<div>Parameters</div>}
            showInputPanel={true}
            nodeId="node-1"
            formId="test-form"
            onClose={onClose}
            mode="edit"
          />
        </>
      )

      const form = screen.getByTestId<HTMLFormElement>('test-form')
      const submitSpy = vi.spyOn(form, 'requestSubmit')

      await user.click(screen.getByRole('button', { name: /Update/i }))

      expect(submitSpy).toHaveBeenCalled()
      expect(onClose).not.toHaveBeenCalled()
    })

    it('calls onClose when Update button is clicked with formId but element is not a form', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(
        <>
          <div id="test-form">Not a form</div>
          <StepEditorLayout
            parametersContent={<div>Parameters</div>}
            showInputPanel={true}
            nodeId="node-1"
            formId="test-form"
            onClose={onClose}
            mode="edit"
          />
        </>
      )

      await user.click(screen.getByRole('button', { name: /Update/i }))

      expect(onClose).toHaveBeenCalled()
    })

    it('calls onClose when Update button is clicked without formId', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(
        <StepEditorLayout
          parametersContent={<div>Parameters</div>}
          showInputPanel={true}
          nodeId="node-1"
          onClose={onClose}
          mode="edit"
        />
      )

      await user.click(screen.getByRole('button', { name: /Update/i }))

      expect(onClose).toHaveBeenCalled()
    })

    it('displays Update button in edit mode', () => {
      render(
        <StepEditorLayout
          parametersContent={<div>Parameters</div>}
          showInputPanel={true}
          nodeId="node-1"
          onClose={vi.fn()}
          mode="edit"
        />
      )

      expect(screen.getByRole('button', { name: /Update/i })).toBeInTheDocument()
    })

    it('defaults to edit mode when mode prop is not provided', () => {
      render(
        <StepEditorLayout
          parametersContent={<div>Parameters</div>}
          showInputPanel={true}
          nodeId="node-1"
          onClose={vi.fn()}
        />
      )

      expect(screen.getByRole('button', { name: /Update/i })).toBeInTheDocument()
    })
  })

  describe('Create button (add mode)', () => {
    it('calls form submit when Create button is clicked with formId in add mode', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(
        <>
          <form id="test-form" data-testid="test-form">
            <input type="text" />
          </form>
          <StepEditorLayout
            parametersContent={<div>Parameters</div>}
            showInputPanel={true}
            nodeId="node-1"
            formId="test-form"
            onClose={onClose}
            mode="add"
          />
        </>
      )

      const form = screen.getByTestId<HTMLFormElement>('test-form')
      const submitSpy = vi.spyOn(form, 'requestSubmit')

      await user.click(screen.getByRole('button', { name: /Create/i }))

      expect(submitSpy).toHaveBeenCalled()
      expect(onClose).not.toHaveBeenCalled()
    })

    it('calls onClose when Create button is clicked with formId but element is not a form', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(
        <>
          <div id="test-form">Not a form</div>
          <StepEditorLayout
            parametersContent={<div>Parameters</div>}
            showInputPanel={true}
            nodeId="node-1"
            formId="test-form"
            onClose={onClose}
            mode="add"
          />
        </>
      )

      await user.click(screen.getByRole('button', { name: /Create/i }))

      expect(onClose).toHaveBeenCalled()
    })

    it('calls onClose when Create button is clicked without formId', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(
        <StepEditorLayout
          parametersContent={<div>Parameters</div>}
          showInputPanel={true}
          nodeId="node-1"
          onClose={onClose}
          mode="add"
        />
      )

      await user.click(screen.getByRole('button', { name: /Create/i }))

      expect(onClose).toHaveBeenCalled()
    })

    it('displays Create button in add mode', () => {
      render(
        <StepEditorLayout
          parametersContent={<div>Parameters</div>}
          showInputPanel={true}
          nodeId="node-1"
          onClose={vi.fn()}
          mode="add"
        />
      )

      expect(screen.getByRole('button', { name: /Create/i })).toBeInTheDocument()
    })
  })

  it('does not render action buttons when showClose is false', () => {
    render(
      <StepEditorLayout
        parametersContent={<div>Parameters</div>}
        showInputPanel={true}
        nodeId="node-1"
        showClose={false}
      />
    )

    expect(screen.queryByRole('button', { name: /Update/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Create/i })).not.toBeInTheDocument()
  })

  it('renders header icon when provided', () => {
    render(
      <StepEditorLayout
        parametersContent={<div>Parameters</div>}
        showInputPanel={false}
        headerIcon={<span data-testid="custom-icon">Icon</span>}
      />
    )

    expect(screen.getByTestId('custom-icon')).toBeInTheDocument()
  })

  it('renders header content when provided', () => {
    render(
      <StepEditorLayout
        parametersContent={<div>Parameters</div>}
        showInputPanel={false}
        headerContent={<span>Custom Header</span>}
      />
    )

    expect(screen.getByText('Custom Header')).toBeInTheDocument()
  })

  it('renders header actions when provided', () => {
    render(
      <StepEditorLayout
        parametersContent={<div>Parameters</div>}
        showInputPanel={false}
        headerActions={<button type="button">Action</button>}
      />
    )

    expect(screen.getByRole('button', { name: /Action/i })).toBeInTheDocument()
  })

  describe('Cancel button', () => {
    it('renders Cancel button when showClose is true in edit mode', () => {
      render(
        <StepEditorLayout
          parametersContent={<div>Parameters</div>}
          showInputPanel={true}
          nodeId="node-1"
          onClose={vi.fn()}
          mode="edit"
        />
      )

      expect(screen.getByRole('button', { name: /Cancel without saving/i })).toBeInTheDocument()
    })

    it('renders Cancel button when showClose is true in add mode', () => {
      render(
        <StepEditorLayout
          parametersContent={<div>Parameters</div>}
          showInputPanel={true}
          nodeId="node-1"
          onClose={vi.fn()}
          mode="add"
        />
      )

      expect(screen.getByRole('button', { name: /Cancel step creation/i })).toBeInTheDocument()
    })

    it('calls onClose when Cancel button is clicked without form submission in edit mode', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(
        <>
          <form id="test-form" data-testid="test-form">
            <input type="text" />
          </form>
          <StepEditorLayout
            parametersContent={<div>Parameters</div>}
            showInputPanel={true}
            nodeId="node-1"
            formId="test-form"
            onClose={onClose}
            mode="edit"
          />
        </>
      )

      const form = screen.getByTestId<HTMLFormElement>('test-form')
      const submitSpy = vi.spyOn(form, 'requestSubmit')

      await user.click(screen.getByRole('button', { name: /Cancel without saving/i }))

      expect(onClose).toHaveBeenCalled()
      expect(submitSpy).not.toHaveBeenCalled()
    })

    it('calls onClose when Cancel button is clicked without form submission in add mode', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      render(
        <>
          <form id="test-form" data-testid="test-form">
            <input type="text" />
          </form>
          <StepEditorLayout
            parametersContent={<div>Parameters</div>}
            showInputPanel={true}
            nodeId="node-1"
            formId="test-form"
            onClose={onClose}
            mode="add"
          />
        </>
      )

      const form = screen.getByTestId<HTMLFormElement>('test-form')
      const submitSpy = vi.spyOn(form, 'requestSubmit')

      await user.click(screen.getByRole('button', { name: /Cancel step creation/i }))

      expect(onClose).toHaveBeenCalled()
      expect(submitSpy).not.toHaveBeenCalled()
    })

    it('does not render Cancel button when showClose is false', () => {
      render(
        <StepEditorLayout
          parametersContent={<div>Parameters</div>}
          showInputPanel={true}
          nodeId="node-1"
          showClose={false}
        />
      )

      expect(screen.queryByRole('button', { name: /Cancel/i })).not.toBeInTheDocument()
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <StepEditorLayout parametersContent={<div>Parameters</div>} showInputPanel={true} nodeId="node-1" />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('does not render navigation arrows when showNavigation is false', () => {
    render(
      <StepEditorLayout
        parametersContent={<div>Parameters</div>}
        showInputPanel={true}
        nodeId="node-1"
        showNavigation={false}
        onNavigateToStep={vi.fn()}
      />
    )

    expect(screen.queryByTestId('nav-arrow-previous')).not.toBeInTheDocument()
    expect(screen.queryByTestId('nav-arrow-next')).not.toBeInTheDocument()
  })

  it('renders navigation arrows when showNavigation is true and neighbors exist', async () => {
    const user = userEvent.setup()
    const onNavigateToStep = vi.fn()
    mockUseAdjacentSteps.mockReturnValue({
      upstream: [{ id: 'prev-node', name: 'Previous', type: 'action' }],
      downstream: [{ id: 'next-node', name: 'Next', type: 'action' }],
    })

    render(
      <StepEditorLayout
        parametersContent={<div>Parameters</div>}
        showInputPanel={true}
        nodeId="node-1"
        showNavigation={true}
        onNavigateToStep={onNavigateToStep}
      />
    )

    expect(screen.getByTestId('nav-arrow-previous')).toBeInTheDocument()
    expect(screen.getByTestId('nav-arrow-next')).toBeInTheDocument()

    await user.click(screen.getByTestId('nav-arrow-previous'))
    expect(onNavigateToStep).toHaveBeenCalledWith('prev-node')
  })

  describe('DocumentationButton', () => {
    it('renders an enabled external link when docLink is provided', () => {
      render(
        <StepEditorLayout
          parametersContent={<div>Parameters</div>}
          showInputPanel={false}
          docLink="https://docs.ansible.com/workflows"
        />
      )

      const link = screen.getByRole('link', { name: /Documentation/i })
      expect(link).toHaveAttribute('href', 'https://docs.ansible.com/workflows')
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noopener noreferrer')
      expect(link).not.toBeDisabled()
    })

    it('hides the Documentation control when docLink is not provided', () => {
      render(<StepEditorLayout parametersContent={<div>Parameters</div>} showInputPanel={false} />)

      expect(screen.queryByRole('link', { name: /Documentation/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Documentation/i })).not.toBeInTheDocument()
    })
  })
})
