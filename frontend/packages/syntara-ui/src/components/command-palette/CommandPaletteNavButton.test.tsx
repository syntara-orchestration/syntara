import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { CommandPaletteNavButton } from './CommandPaletteNavButton'

const mockOpen = vi.fn()

vi.mock('./useCommandPalette', () => ({
  useCommandPalette: () => ({
    isOpen: false,
    open: mockOpen,
    close: vi.fn(),
    toggle: vi.fn(),
  }),
}))

describe('CommandPaletteNavButton', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(<CommandPaletteNavButton />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('opens the palette when clicked', async () => {
    const user = userEvent.setup()
    render(<CommandPaletteNavButton />)

    await user.click(screen.getByRole('button', { name: /Search \(/ }))
    expect(mockOpen).toHaveBeenCalled()
  })
})
