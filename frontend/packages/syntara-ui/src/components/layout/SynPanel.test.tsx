import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynPanel } from './SynPanel'

describe('SynPanel', () => {
  it('renders children', () => {
    render(<SynPanel>Panel content</SynPanel>)

    expect(screen.getByText('Panel content')).toBeInTheDocument()
  })

  it('renders footer content', () => {
    render(<SynPanel footer={<button>Save</button>}>Panel content</SynPanel>)

    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
    expect(screen.getByText('Panel content')).toBeInTheDocument()
  })

  it('does not render footer when prop is omitted', () => {
    render(<SynPanel>Panel content</SynPanel>)

    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <SynPanel hasNoPadding isFullHeight isScrollable>
        <p>Scrollable region</p>
      </SynPanel>
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with footer', async () => {
    const { container } = render(
      <SynPanel isFullHeight isScrollable footer={<button>Save</button>}>
        <p>Panel with footer</p>
      </SynPanel>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
