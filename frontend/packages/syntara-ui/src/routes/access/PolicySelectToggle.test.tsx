import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { PolicySelectToggle } from './PolicySelectToggle'

describe('PolicySelectToggle', () => {
  const defaultProps = {
    toggleRef: createRef<HTMLButtonElement>(),
    isOpen: false,
    onToggle: vi.fn(),
    filterValue: '',
    onFilterChange: vi.fn(),
    onFilterFocus: vi.fn(),
    selected: [] as string[],
    onRemovePolicy: vi.fn(),
    onClearAll: vi.fn(),
    inputRef: createRef<HTMLInputElement>(),
  }

  it('has no accessibility violations in default state', async () => {
    const { container } = render(<PolicySelectToggle {...defaultProps} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with selected policy chips', async () => {
    const { container } = render(
      <PolicySelectToggle {...defaultProps} selected={['workflow-admin', 'project-viewer']} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders selected policies as SynLabel chips', () => {
    render(<PolicySelectToggle {...defaultProps} selected={['workflow-admin']} />)
    expect(screen.getByText('workflow-admin')).toBeInTheDocument()
  })

  it('calls onClearAll when the clear button is clicked', async () => {
    const user = userEvent.setup()
    const onClearAll = vi.fn()
    render(<PolicySelectToggle {...defaultProps} selected={['workflow-admin']} onClearAll={onClearAll} />)

    await user.click(screen.getByRole('button', { name: 'Clear all selected policies' }))

    expect(onClearAll).toHaveBeenCalledTimes(1)
  })
})
