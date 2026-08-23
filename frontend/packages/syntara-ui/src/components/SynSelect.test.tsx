import { MenuToggle, SelectList, SelectOption } from '@patternfly/react-core'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynSelect } from './SynSelect'

function TestSynSelect({
  onOpenChange,
  isScrollable,
  maxMenuHeight,
  className,
}: Readonly<{
  onOpenChange?: (open: boolean) => void
  isScrollable?: boolean
  maxMenuHeight?: string
  className?: string
}>) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div>
      <SynSelect
        isOpen={isOpen}
        onOpenChange={(open) => {
          setIsOpen(open)
          onOpenChange?.(open)
        }}
        isScrollable={isScrollable}
        maxMenuHeight={maxMenuHeight}
        className={className}
        toggle={(toggleRef) => (
          <MenuToggle ref={toggleRef} onClick={() => setIsOpen((open) => !open)} isExpanded={isOpen}>
            Toggle
          </MenuToggle>
        )}
      >
        <SelectList>
          <SelectOption value="one">One</SelectOption>
          <SelectOption value="two">Two</SelectOption>
        </SelectList>
      </SynSelect>
      <p>Outside</p>
    </div>
  )
}

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

async function openMenu() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Toggle' }))
  return screen.getByRole('listbox')
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
    render(<SelectWithoutHandler />)
    await user.click(screen.getByRole('button', { name: 'Toggle' }))

    expect(() => {
      act(() => {
        screen.getByText('Outside').dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true }))
      })
    }).not.toThrow()
  })

  it('opens with an explicit maxMenuHeight override', async () => {
    render(<TestSynSelect maxMenuHeight="10rem" />)
    expect(await openMenu()).toBeInTheDocument()
  })

  it('opens with a caller className', async () => {
    render(<TestSynSelect className="extra-select-class" />)
    expect(await openMenu()).toBeInTheDocument()
  })

  it('accepts an isScrollable override', async () => {
    render(<TestSynSelect isScrollable={false} />)
    expect(await openMenu()).toBeInTheDocument()
  })

  it('has no accessibility violations when closed', async () => {
    const { container } = render(<TestSynSelect />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations when open', async () => {
    const { container } = render(<TestSynSelect />)
    await openMenu()
    expect(await axe(container)).toHaveNoViolations()
  })
})
