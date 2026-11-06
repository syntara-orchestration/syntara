import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SynStepHeader } from './SynStepHeader'

describe('SynStepHeader', () => {
  it('renders children', () => {
    render(
      <SynStepHeader>
        <span data-testid="child">Header Content</span>
      </SynStepHeader>
    )

    expect(screen.getByTestId('child')).toBeInTheDocument()
    expect(screen.getByTestId('node-header')).toBeInTheDocument()
  })

  it('merges optional className', () => {
    render(
      <SynStepHeader className="custom-header">
        <span>Content</span>
      </SynStepHeader>
    )

    expect(screen.getByTestId('node-header')).toHaveClass('custom-header')
  })
})
