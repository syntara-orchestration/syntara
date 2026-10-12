import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynCodeTruncateCell } from './SynCodeTruncateCell'

describe('SynCodeTruncateCell', () => {
  it('renders content inside a code element', () => {
    render(<SynCodeTruncateCell content="my-long-policy-name" />)

    expect(screen.getByRole('code')).toHaveTextContent('my-long-policy-name')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SynCodeTruncateCell content="viewer-policy" />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
