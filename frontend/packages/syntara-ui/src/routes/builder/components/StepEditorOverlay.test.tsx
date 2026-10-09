import { ExecutorTypeEnum } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RegistryStepId } from '../../../constants'
import type { DocKey } from '../../../utils/docs/types'

import { StepEditorOverlay } from './StepEditorOverlay'

const useDocLinkMock = vi.fn((key: DocKey) => `https://docs.example/${key}`)

vi.mock('../../../utils/docs/useDocLink', () => ({
  useDocLink: (key: DocKey) => useDocLinkMock(key),
}))

vi.mock('../StepDetailsPanel', () => ({
  StepDetailsPanel: ({ mode, docLink }: { mode: string; docLink?: string }) => (
    <div data-testid="step-details-panel">
      {mode}
      {docLink ? <span data-testid="doc-link">{docLink}</span> : null}
    </div>
  ),
}))

describe('StepEditorOverlay', () => {
  const baseProps = {
    isOpen: true,
    mode: 'edit' as const,
    selectedNode: {
      id: 'task-1',
      type: 'task',
      position: { x: 0, y: 0 },
      data: { id: 'task-1', type: ExecutorTypeEnum.SCRIPT, name: 'Task' },
    } as never,
    stepTypeId: null,
    stepSubtypeId: null,
    sourceNodeId: null,
    replacementNodeId: null,
    onConnect: vi.fn(),
    onClose: vi.fn(),
  }

  beforeEach(() => {
    useDocLinkMock.mockClear()
  })

  it('renders nothing when closed', () => {
    const { container } = render(<StepEditorOverlay {...baseProps} isOpen={false} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders StepDetailsPanel when open', () => {
    render(<StepEditorOverlay {...baseProps} />)
    expect(screen.getByTestId('step-details-panel')).toHaveTextContent('edit')
  })

  it('passes mode as add when mode prop is add', () => {
    render(<StepEditorOverlay {...baseProps} mode="add" stepTypeId="script" selectedNode={null} />)
    expect(screen.getByTestId('step-details-panel')).toHaveTextContent('add')
  })

  it('omits docLink for script steps', () => {
    render(<StepEditorOverlay {...baseProps} />)
    expect(screen.getByTestId('step-details-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('doc-link')).not.toBeInTheDocument()
  })

  it('passes step-specific docLink for edit mode based on executor type', () => {
    render(
      <StepEditorOverlay
        {...baseProps}
        selectedNode={{
          id: 'task-1',
          type: 'task',
          position: { x: 0, y: 0 },
          data: { id: 'task-1', type: ExecutorTypeEnum.HTTP_REQUEST, name: 'Task' },
        }}
      />
    )
    expect(useDocLinkMock).toHaveBeenCalledWith('restApi')
    expect(screen.getByTestId('doc-link')).toHaveTextContent('https://docs.example/restApi')
  })

  it('passes step-specific docLink for add mode based on subtype', () => {
    render(
      <StepEditorOverlay
        {...baseProps}
        mode="add"
        selectedNode={null}
        stepTypeId={RegistryStepId.LOGIC}
        stepSubtypeId={RegistryStepId.LOGIC_WAIT}
      />
    )
    expect(useDocLinkMock).toHaveBeenCalledWith('wait')
    expect(screen.getByTestId('doc-link')).toHaveTextContent('https://docs.example/wait')
  })

  it('falls back to builder docLink when step type is unknown', () => {
    render(
      <StepEditorOverlay
        {...baseProps}
        mode="add"
        selectedNode={null}
        stepTypeId={RegistryStepId.ACTION}
        stepSubtypeId={null}
      />
    )
    expect(useDocLinkMock).toHaveBeenCalledWith('builder')
    expect(screen.getByTestId('doc-link')).toHaveTextContent('https://docs.example/builder')
  })
})
