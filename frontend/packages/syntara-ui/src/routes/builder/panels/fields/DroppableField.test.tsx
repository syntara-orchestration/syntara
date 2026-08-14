import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { DroppableField } from './DroppableField'

describe('DroppableField', () => {
  it('renders children', () => {
    render(
      <DroppableField onDropText={vi.fn()}>
        <input aria-label="Test input" />
      </DroppableField>
    )

    expect(screen.getByRole('textbox', { name: 'Test input' })).toBeInTheDocument()
  })

  it('calls onDropText with text/plain data on drop from internal source', () => {
    const onDropText = vi.fn()
    render(
      <DroppableField onDropText={onDropText}>
        <input aria-label="Test input" />
      </DroppableField>
    )

    const input = screen.getByRole('textbox', { name: 'Test input' })

    fireEvent.drop(input, {
      dataTransfer: {
        getData: (type: string) => {
          if (type === 'application/json') return '{"type":"syntara/input-field"}'
          if (type === 'text/plain') return '${node1.output}'
          return ''
        },
      },
    })

    expect(onDropText).toHaveBeenCalledWith('${node1.output}')
  })

  it('rejects drops from external sources without application/json', () => {
    const onDropText = vi.fn()
    render(
      <DroppableField onDropText={onDropText}>
        <input aria-label="Test input" />
      </DroppableField>
    )

    const input = screen.getByRole('textbox', { name: 'Test input' })

    fireEvent.drop(input, {
      dataTransfer: {
        getData: (type: string) => (type === 'text/plain' ? 'malicious content' : ''),
      },
    })

    expect(onDropText).not.toHaveBeenCalled()
  })

  it('does not call onDropText when dropped text is empty', () => {
    const onDropText = vi.fn()
    render(
      <DroppableField onDropText={onDropText}>
        <input aria-label="Test input" />
      </DroppableField>
    )

    const input = screen.getByRole('textbox', { name: 'Test input' })

    fireEvent.drop(input, {
      dataTransfer: {
        getData: () => '',
      },
    })

    expect(onDropText).not.toHaveBeenCalled()
  })

  it('does not call onDropText when isDisabled is true', () => {
    const onDropText = vi.fn()
    render(
      <DroppableField onDropText={onDropText} isDisabled>
        <input aria-label="Test input" />
      </DroppableField>
    )

    const input = screen.getByRole('textbox', { name: 'Test input' })

    fireEvent.drop(input, {
      dataTransfer: {
        getData: (type: string) => {
          if (type === 'application/json') return '{"type":"syntara/input-field"}'
          if (type === 'text/plain') return '${node1.output}'
          return ''
        },
      },
    })

    expect(onDropText).not.toHaveBeenCalled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <DroppableField onDropText={vi.fn()}>
        <label htmlFor="test-input">Test field</label>
        <input id="test-input" aria-label="Test input" />
      </DroppableField>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
