import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CommandPaletteProvider } from './CommandPaletteProvider'
import { useCommandPalette } from './useCommandPalette'

vi.mock('./CommandPalette', () => ({
  CommandPalette: ({ isOpen }: { isOpen: boolean }) => (isOpen ? <div>palette-open</div> : null),
}))

function PaletteProbe() {
  const { open } = useCommandPalette()
  return (
    <button type="button" onClick={open}>
      Open search
    </button>
  )
}

describe('CommandPaletteProvider', () => {
  it('opens the palette from a consumer and from Ctrl+K', async () => {
    const user = userEvent.setup()
    render(
      <CommandPaletteProvider>
        <PaletteProbe />
      </CommandPaletteProvider>
    )

    expect(screen.queryByText('palette-open')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Open search' }))
    expect(screen.getByText('palette-open')).toBeInTheDocument()

    await user.keyboard('{Control>}k{/Control}')
    expect(screen.queryByText('palette-open')).not.toBeInTheDocument()
  })

  it('throws when useCommandPalette is used outside the provider', () => {
    expect(() => render(<PaletteProbe />)).toThrow('useCommandPalette must be used within CommandPaletteProvider')
  })
})
