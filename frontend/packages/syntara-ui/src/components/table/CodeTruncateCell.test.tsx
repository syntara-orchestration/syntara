import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { CodeTruncateCell } from './CodeTruncateCell'

describe('CodeTruncateCell', () => {
  it('renders content inside a code element', () => {
    render(<CodeTruncateCell content="my-long-policy-name" />)

    expect(screen.getByRole('code')).toHaveTextContent('my-long-policy-name')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<CodeTruncateCell content="viewer-policy" />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
