import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FieldHelpIcon } from './FieldHelpIcon'

describe('FieldHelpIcon', () => {
  it('renders the help icon', () => {
    const { container } = render(<FieldHelpIcon />)
    expect(container).not.toBeEmptyDOMElement()
  })
})
