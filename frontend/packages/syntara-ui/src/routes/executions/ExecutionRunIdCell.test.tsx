import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ExecutionRunIdCell } from './ExecutionRunIdCell'

vi.mock('@tanstack/react-router', async () => ({
  ...(await vi.importActual<typeof import('@tanstack/react-router')>('@tanstack/react-router')),
  Link: ({ to, params, children }: { to: string; params?: Record<string, string>; children: React.ReactNode }) => {
    const href = Object.entries(params ?? {}).reduce(
      (path, [key, value]) => path.replaceAll(`$${key}`, encodeURIComponent(value)),
      to
    )
    return <a href={href}>{children}</a>
  },
}))

describe('ExecutionRunIdCell', () => {
  it('renders the execution id as a link to its detail page', () => {
    const executionId = '623e4567-e89b-12d3-a456-426614174005'
    render(<ExecutionRunIdCell executionId={executionId} />)

    expect(screen.getByRole('link', { name: executionId })).toHaveAttribute('href', `/executions/${executionId}`)
  })

  it('renders truncated execution ids inside a code element', () => {
    const executionId = '723e4567-e89b-12d3-a456-426614174006-extra-long-suffix'
    render(<ExecutionRunIdCell executionId={executionId} />)

    expect(screen.getByRole('code')).toHaveTextContent(executionId)
  })
})
