import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { useCanI } from '../../hooks/useCanI'

import { RetryFromFailureButton } from './RetryFromFailureButton'

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

function renderButton(props?: Partial<React.ComponentProps<typeof RetryFromFailureButton>>) {
  const defaultProps = { projectId: 'project-1', ...props }
  return render(<RetryFromFailureButton {...defaultProps} />)
}

describe('RetryFromFailureButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })
  })

  it('renders an enabled retry-from-failure button', () => {
    renderButton()
    const button = screen.getByRole('button', { name: 'Retry run from failure' })
    expect(button).toBeInTheDocument()
    expect(button).toBeEnabled()
  })

  it('calls the open-panel handler on click', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    renderButton({ onClick })

    await user.click(screen.getByRole('button', { name: 'Retry run from failure' }))

    expect(onClick).toHaveBeenCalledOnce()
  })

  it('passes resourceProject to useCanI', () => {
    renderButton({ projectId: 'proj-42' })

    expect(useCanI).toHaveBeenCalledWith('run', 'execution', { resourceProject: 'proj-42' })
  })

  it('is aria-disabled when the user lacks execution:run permission', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })

    renderButton()

    const button = screen.getByRole('button', { name: 'Retry run from failure' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('is aria-disabled while the permission check is in flight', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: true, isError: false })

    renderButton()

    const button = screen.getByRole('button', { name: 'Retry run from failure' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('does not open the panel when the button is disabled', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    const user = userEvent.setup()
    const onClick = vi.fn()
    renderButton({ onClick })

    await user.click(screen.getByRole('button', { name: 'Retry run from failure' }))

    expect(onClick).not.toHaveBeenCalled()
  })

  it('disables the dropdown item when the user lacks retry permission', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    const user = userEvent.setup()
    const onClick = vi.fn()
    renderButton({ asDropdownItem: true, onClick })
    const menuItem = screen.getByRole('menuitem', { name: 'Retry run from failure' })

    expect(menuItem).toHaveAttribute('aria-disabled', 'true')
    await user.click(menuItem)

    expect(onClick).not.toHaveBeenCalled()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderButton()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
