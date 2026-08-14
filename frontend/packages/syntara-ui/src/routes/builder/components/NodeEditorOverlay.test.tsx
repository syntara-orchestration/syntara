import { ExecutorTypeEnum } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RegistryNodeId } from '../../../constants'
import type { DocKey } from '../../../utils/docs/types'

import { NodeEditorOverlay } from './NodeEditorOverlay'

const useDocLinkMock = vi.fn((key: DocKey) => `https://docs.example/${key}`)

vi.mock('../../../utils/docs/useDocLink', () => ({
  useDocLink: (key: DocKey) => useDocLinkMock(key),
}))

vi.mock('../NodeDetailsPanel', () => ({
  NodeDetailsPanel: ({ mode, docLink }: { mode: string; docLink?: string }) => (
    <div data-testid="node-details-panel">
      {mode}
      {docLink ? <span data-testid="doc-link">{docLink}</span> : null}
    </div>
  ),
}))

describe('NodeEditorOverlay', () => {
  const baseProps = {
    isOpen: true,
    mode: 'edit' as const,
    selectedNode: {
      id: 'task-1',
      type: 'task',
      position: { x: 0, y: 0 },
      data: { id: 'task-1', type: ExecutorTypeEnum.SCRIPT, name: 'Task' },
    } as never,
    nodeTypeId: null,
    nodeSubtypeId: null,
    sourceNodeId: null,
    replacementNodeId: null,
    onConnect: vi.fn(),
    onClose: vi.fn(),
  }

  beforeEach(() => {
    useDocLinkMock.mockClear()
  })

  it('renders nothing when closed', () => {
    const { container } = render(<NodeEditorOverlay {...baseProps} isOpen={false} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders NodeDetailsPanel when open', () => {
    render(<NodeEditorOverlay {...baseProps} />)
    expect(screen.getByTestId('node-details-panel')).toHaveTextContent('edit')
  })

  it('passes mode as add when mode prop is add', () => {
    render(<NodeEditorOverlay {...baseProps} mode="add" nodeTypeId="script" selectedNode={null} />)
    expect(screen.getByTestId('node-details-panel')).toHaveTextContent('add')
  })

  it('omits docLink for script steps', () => {
    render(<NodeEditorOverlay {...baseProps} />)
    expect(screen.getByTestId('node-details-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('doc-link')).not.toBeInTheDocument()
  })

  it('passes step-specific docLink for edit mode based on executor type', () => {
    render(
      <NodeEditorOverlay
        {...baseProps}
        selectedNode={
          {
            id: 'task-1',
            type: 'task',
            position: { x: 0, y: 0 },
            data: { id: 'task-1', type: ExecutorTypeEnum.HTTP_REQUEST, name: 'Task' },
          } as never
        }
      />
    )
    expect(useDocLinkMock).toHaveBeenCalledWith('restApi')
    expect(screen.getByTestId('doc-link')).toHaveTextContent('https://docs.example/restApi')
  })

  it('passes step-specific docLink for add mode based on subtype', () => {
    render(
      <NodeEditorOverlay
        {...baseProps}
        mode="add"
        selectedNode={null}
        nodeTypeId={RegistryNodeId.LOGIC}
        nodeSubtypeId={RegistryNodeId.LOGIC_WAIT}
      />
    )
    expect(useDocLinkMock).toHaveBeenCalledWith('wait')
    expect(screen.getByTestId('doc-link')).toHaveTextContent('https://docs.example/wait')
  })

  it('falls back to builder docLink when step type is unknown', () => {
    render(
      <NodeEditorOverlay
        {...baseProps}
        mode="add"
        selectedNode={null}
        nodeTypeId={RegistryNodeId.ACTION}
        nodeSubtypeId={null}
      />
    )
    expect(useDocLinkMock).toHaveBeenCalledWith('builder')
    expect(screen.getByTestId('doc-link')).toHaveTextContent('https://docs.example/builder')
  })
})
