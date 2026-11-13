import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { WorkflowBuilderIcon } from './WorkflowBuilderIcon'

describe('WorkflowBuilderIcon', () => {
  it('rotates the network glyph to match the workflow trigger prototype', () => {
    render(<WorkflowBuilderIcon className="workflow-builder-icon" />)
    const icon = screen.getByTestId('workflow-builder-icon')

    expect(icon).toHaveClass('workflow-builder-icon')
    expect(icon).toHaveStyle({ transform: 'rotate(270deg)' })
  })

  it('has no accessibility violations as a decorative icon', async () => {
    const { container } = render(<WorkflowBuilderIcon />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
