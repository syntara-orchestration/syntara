import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { EXECUTION_PLANE_SCOPE_HELP } from '../integrationFieldHelpText'

import { ExecutionPlaneScopeField } from './ExecutionPlaneScopeField'

describe('ExecutionPlaneScopeField', () => {
  it('renders locked Global scope with execution-plane helper text', () => {
    render(<ExecutionPlaneScopeField fieldId="test-scope" />)

    expect(screen.getByText('Global')).toBeInTheDocument()
    expect(screen.getByText(EXECUTION_PLANE_SCOPE_HELP)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ExecutionPlaneScopeField fieldId="test-scope" />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
