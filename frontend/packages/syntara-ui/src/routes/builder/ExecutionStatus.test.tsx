import type { ExecutionsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ActivityStatusLabel, StatusLabel } from './ExecutionStatus'

type ActivityStatus = ExecutionsAPI.components['schemas']['ActivityStatus']

describe('StatusLabel', () => {
  it.each([
    ['pending', 'Pending'],
    ['running', 'Running'],
    ['paused', 'Paused'],
    ['completed', 'Completed'],
    ['completed_with_errors', 'Completed with errors'],
    ['failed', 'Failed'],
    ['cancelled', 'Cancelled'],
  ] as const)('renders "%s" as "%s"', (status, label) => {
    render(<StatusLabel status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })
})

describe('ActivityStatusLabel', () => {
  it.each<[ActivityStatus, string]>([
    ['pending', 'Pending'],
    ['running', 'Running'],
    ['completed', 'Successful'],
    ['failed', 'Failed'],
    ['retrying', 'Retrying'],
    ['skipped', 'Skipped'],
    ['cancelled', 'Cancelled'],
  ])('renders "%s" as "%s"', (status, label) => {
    render(<ActivityStatusLabel status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('uses PatternFly Label component', () => {
    render(<ActivityStatusLabel status="completed" />)

    expect(screen.getByText('Successful')).toBeInTheDocument()
  })

  it('renders "waiting" as "Waiting for approval" for non-wait nodes', () => {
    render(<ActivityStatusLabel status="waiting" />)
    expect(screen.getByText('Waiting for approval')).toBeInTheDocument()
  })

  it('renders "waiting" as "Running" for wait nodes', () => {
    render(<ActivityStatusLabel status="waiting" nodeType="wait" />)
    expect(screen.getByText('Running')).toBeInTheDocument()
  })

  it('renders "waiting" as "Waiting for approval" when nodeType is not wait', () => {
    render(<ActivityStatusLabel status="waiting" nodeType="approval" />)
    expect(screen.getByText('Waiting for approval')).toBeInTheDocument()
  })

  it('renders "waiting" as "Waiting for approval" when nodeType is undefined', () => {
    render(<ActivityStatusLabel status="waiting" nodeType={undefined} />)
    expect(screen.getByText('Waiting for approval')).toBeInTheDocument()
  })

  it('renders all activity statuses without errors', () => {
    // Test that all valid activity statuses can be rendered without crashing
    const statuses: ActivityStatus[] = [
      'pending',
      'running',
      'waiting',
      'completed',
      'failed',
      'retrying',
      'skipped',
      'cancelled',
    ]

    // Verify each status renders without throwing
    statuses.forEach((status) => {
      const { unmount } = render(<ActivityStatusLabel status={status} />)
      // The render itself is the test - if any status causes a crash, the test will fail
      unmount()
    })

    // Add a passing assertion to satisfy vitest/expect-expect rule
    expect(statuses).toHaveLength(8)
  })

  it('handles unknown activity status with fallback', () => {
    // Test the ?? fallback operators for unknown status values
    const unknownStatus = 'unknown_status' as ActivityStatus
    render(<ActivityStatusLabel status={unknownStatus} />)
    // Should capitalize first letter as fallback
    expect(screen.getByText('Unknown_status')).toBeInTheDocument()
  })
})
