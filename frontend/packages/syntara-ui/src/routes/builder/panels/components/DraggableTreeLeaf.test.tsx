import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { CopyExpressionAction, DraggableTreeLeaf } from './DraggableTreeLeaf'

describe('DraggableTreeLeaf', () => {
  it('renders label', () => {
    render(<DraggableTreeLeaf label="S hostname" onDragStart={vi.fn()} />)

    expect(screen.getByText('S hostname')).toBeInTheDocument()
  })

  it('renders secondary text when provided', () => {
    render(<DraggableTreeLeaf label="S hostname" secondaryText="server-01" onDragStart={vi.fn()} />)

    expect(screen.getByText('server-01')).toBeInTheDocument()
  })

  it('has draggable attribute and fires onDragStart when dragged', () => {
    const onDragStart = vi.fn()
    render(<DraggableTreeLeaf label="S hostname" onDragStart={onDragStart} />)

    const leaf = screen.getByText('S hostname')
    // eslint-disable-next-line testing-library/no-node-access -- closest() is the only way to assert the draggable attribute lives on an ancestor element
    expect(leaf.closest('[draggable="true"]')).toBeInTheDocument()
    fireEvent.dragStart(leaf)
    expect(onDragStart).toHaveBeenCalledTimes(1)
  })

  it('can disable dragging', () => {
    render(<DraggableTreeLeaf label="S hostname" draggable={false} />)

    const leaf = screen.getByText('S hostname')
    // eslint-disable-next-line testing-library/no-node-access -- closest() is the only way to assert the draggable attribute lives on an ancestor element
    expect(leaf.closest('[draggable="false"]')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <DraggableTreeLeaf label="S hostname" secondaryText="server-01" onDragStart={vi.fn()} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('CopyExpressionAction', () => {
  const originalClipboard = navigator.clipboard
  let mockWriteText: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockWriteText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: mockWriteText },
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: originalClipboard,
      writable: true,
      configurable: true,
    })
    vi.restoreAllMocks()
  })

  it('renders a copy button with accessible label', () => {
    render(<CopyExpressionAction expressionText="${step_1.hostname}" />)

    expect(screen.getByRole('button', { name: /copy expression/i })).toBeInTheDocument()
  })

  it('copies expression to clipboard when clicked', async () => {
    const user = userEvent.setup()
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: mockWriteText },
      writable: true,
      configurable: true,
    })

    render(<CopyExpressionAction expressionText="${step_1.hostname}" />)

    await user.click(screen.getByRole('button', { name: /copy expression/i }))

    await waitFor(() => {
      expect(mockWriteText).toHaveBeenCalledWith('${step_1.hostname}')
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<CopyExpressionAction expressionText="${step_1.hostname}" />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
