import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { PolicyJsonModal } from './PolicyJsonModal'
import type { PolicyRead } from './types'

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../components/details/SynCodeBlock', () => ({
  SynCodeBlock: ({ jsonObject }: { jsonObject: unknown }) => <pre>{JSON.stringify(jsonObject)}</pre>,
}))

const samplePolicy: PolicyRead = {
  id: 'p1',
  name: 'admin-policy',
  description: 'Full admin access',
  scope: 'any',
  statements: [{ scope: 'any', effect: 'allow', actions: ['workflow:read'] }],
  is_builtin: true,
  is_project_eligible: false,
  is_system_scoped: true,
  project_id: null,
  labels: {},
  created_at: '2024-01-01T00:00:00Z',
  updated_at: null,
}

describe('PolicyJsonModal', () => {
  const onClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders policy-specific title and formatted policy payload', () => {
    render(<PolicyJsonModal isOpen policy={samplePolicy} onClose={onClose} />)

    expect(screen.getByRole('heading', { name: 'admin-policy policy definition' })).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/"name":"admin-policy"/)).toBeInTheDocument()
  })

  it('calls onClose when primary Close is clicked', async () => {
    const user = userEvent.setup()
    render(<PolicyJsonModal isOpen policy={samplePolicy} onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: 'Close policy definition' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when Escape is pressed', async () => {
    const user = userEvent.setup()
    render(<PolicyJsonModal isOpen policy={samplePolicy} onClose={onClose} />)

    await user.keyboard('{Escape}')

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not render dialog content when closed', () => {
    render(<PolicyJsonModal isOpen={false} policy={samplePolicy} onClose={onClose} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('handles re-render with unchanged props', () => {
    const { rerender } = render(<PolicyJsonModal isOpen policy={samplePolicy} onClose={onClose} />)
    rerender(<PolicyJsonModal isOpen policy={samplePolicy} onClose={onClose} />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<PolicyJsonModal isOpen policy={samplePolicy} onClose={onClose} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
