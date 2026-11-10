import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynKebabMenu } from '../../components/SynKebabMenu'

import { buildExecutionTargetTestConnectionAction } from './executionTargetTestConnectionAction'

const target = {
  id: 'et-001',
  cluster_id: 'cl-001',
  name: 'Prod OpenShift West',
  backend_type: 'kubernetes' as const,
  endpoint: 'https://api.west.example.com',
  placement: {
    type: 'kubernetes' as const,
    namespace: 'syntara-workers',
    node_selectors: [] as string[],
    tolerations: [] as string[],
  },
  status: 'active' as const,
  enabled: true,
  is_default: true,
  status_message: null,
  labels: {},
  created_at: '2026-01-01T00:00:00Z',
  last_ran_at: null,
}

describe('buildExecutionTargetTestConnectionAction', () => {
  it('builds an enabled Test connection action', () => {
    const onTest = vi.fn()
    const action = buildExecutionTargetTestConnectionAction(target, onTest)

    expect(action.key).toBe('test-connection')
    expect(action.isAriaDisabled).toBe(false)
    action.onClick?.()
    expect(onTest).toHaveBeenCalledWith(target)
  })

  it('disables the action while a connection test is pending', () => {
    const onTest = vi.fn()
    const action = buildExecutionTargetTestConnectionAction(target, onTest, { isDisabled: true })

    expect(action.isAriaDisabled).toBe(true)
    expect(action.onClick).toBeUndefined()
    expect(action.tooltipProps?.content).toBe('Connection test in progress')
  })

  it('has no accessibility violations in the kebab', async () => {
    const action = buildExecutionTargetTestConnectionAction(target, vi.fn())
    const { container } = render(<SynKebabMenu actions={[action]} aria-label="Actions for Prod OpenShift West" />)

    expect(await axe(container)).toHaveNoViolations()
    expect(screen.getByRole('button', { name: 'Actions for Prod OpenShift West' })).toBeInTheDocument()
  })
})
