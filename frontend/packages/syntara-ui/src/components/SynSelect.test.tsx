import { MenuToggle, SelectList, SelectOption } from '@patternfly/react-core'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { SynSelect } from './SynSelect'

function TestSynSelect({ onOpenChange }: Readonly<{ onOpenChange?: (open: boolean) => void }>) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div>
      <SynSelect
        isOpen={isOpen}
        onOpenChange={(open) => {
          setIsOpen(open)
          onOpenChange?.(open)
        }}
        toggle={(toggleRef) => (
          <MenuToggle ref={toggleRef} onClick={() => setIsOpen((open) => !open)} isExpanded={isOpen}>
            Toggle
          </MenuToggle>
        )}
      >
        <SelectList>
          <SelectOption value="one">One</SelectOption>
        </SelectList>
      </SynSelect>
      <p>Outside</p>
    </div>
  )
}

describe('SynSelect', () => {
  it('closes when wheel happens outside the menu', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(<TestSynSelect onOpenChange={onOpenChange} />)

    await user.click(screen.getByRole('button', { name: 'Toggle' }))
    expect(screen.getByRole('listbox')).toBeInTheDocument()

    act(() => {
      screen.getByText('Outside').dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true }))
    })

    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('keeps the menu open when wheel happens on an option', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(<TestSynSelect onOpenChange={onOpenChange} />)

    await user.click(screen.getByRole('button', { name: 'Toggle' }))
    const option = screen.getByRole('option', { name: 'One' })

    act(() => {
      option.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true }))
    })

    expect(screen.getByRole('listbox')).toBeInTheDocument()
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })

  it('does not throw when onOpenChange is omitted and the menu is dismissed', async () => {
    const user = userEvent.setup()

    function SelectWithoutHandler() {
      const [isOpen, setIsOpen] = useState(false)
      return (
        <div>
          <SynSelect
            isOpen={isOpen}
            toggle={(toggleRef) => (
              <MenuToggle ref={toggleRef} onClick={() => setIsOpen((open) => !open)} isExpanded={isOpen}>
                Toggle
              </MenuToggle>
            )}
          >
            <SelectList>
              <SelectOption value="one">One</SelectOption>
            </SelectList>
          </SynSelect>
          <p>Outside</p>
        </div>
      )
    }

    render(<SelectWithoutHandler />)
    await user.click(screen.getByRole('button', { name: 'Toggle' }))

    expect(() => {
      act(() => {
        screen.getByText('Outside').dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true }))
      })
    }).not.toThrow()
  })
})
