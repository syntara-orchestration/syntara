import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { FieldHelpIcon } from './FieldHelpIcon'

describe('FieldHelpIcon', () => {
  it('renders the help icon', () => {
    const { container } = render(<FieldHelpIcon />)
    expect(container).not.toBeEmptyDOMElement()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<FieldHelpIcon />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
