import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { FormPromptUnresolvedDynamicOptionsAlert } from './FormPromptUnresolvedDynamicOptionsAlert'

describe('FormPromptUnresolvedDynamicOptionsAlert', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(<FormPromptUnresolvedDynamicOptionsAlert />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
