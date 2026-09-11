import { MenuToggle, SelectList, SelectOption } from '@patternfly/react-core'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { type ComponentProps, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { LONG_SELECT_MAX_MENU_HEIGHT } from './longSelectMenu'
import longSelectMenuStyles from './longSelectMenu.module.css'
import { SynSelect } from './SynSelect'

function TestSynSelect({
  onOpenChange,
  isScrollable,
  maxMenuHeight,
  className,
  popperProps,
}: Readonly<{
  onOpenChange?: (open: boolean) => void
  isScrollable?: boolean
  maxMenuHeight?: string
  className?: string
  popperProps?: ComponentProps<typeof SynSelect>['popperProps']
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
        popperProps={popperProps}
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

function getOpenMenu() {
  const listbox = screen.getByRole('listbox')
  // PatternFly puts scrollable/className on the Menu root and maxMenuHeight on MenuContent.
  // neither has an accessible role of its own.
  /* eslint-disable testing-library/no-node-access */
  const menu = listbox.closest('.pf-v6-c-menu')
  expect(menu).toBeInstanceOf(HTMLElement)
  return menu as HTMLElement
  /* eslint-enable testing-library/no-node-access */
}

function getMenuContentMaxHeight(menu: HTMLElement) {
  /* eslint-disable testing-library/no-node-access */
  const content = menu.querySelector('.pf-v6-c-menu__content')
  /* eslint-enable testing-library/no-node-access */
  expect(content).toBeInstanceOf(HTMLElement)
  return (content as HTMLElement).style.getPropertyValue('--pf-v6-c-menu__content--MaxHeight')
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

  it('applies scrollable menu height defaults when opened', async () => {
    render(<TestSynSelect />)

    await openMenu()

    const menu = getOpenMenu()
    expect(menu).toHaveClass('pf-m-scrollable')
    expect(menu).toHaveClass(longSelectMenuStyles.containScroll)
    expect(getMenuContentMaxHeight(menu)).toBe(LONG_SELECT_MAX_MENU_HEIGHT)
  })

  it('applies an explicit maxMenuHeight override on the open menu', async () => {
    render(<TestSynSelect maxMenuHeight="10rem" />)

    await openMenu()

    expect(getMenuContentMaxHeight(getOpenMenu())).toBe('10rem')
  })

  it('merges a caller className onto the open menu', async () => {
    render(<TestSynSelect className="extra-select-class" />)

    await openMenu()

    const menu = getOpenMenu()
    expect(menu).toHaveClass(longSelectMenuStyles.containScroll)
    expect(menu).toHaveClass('extra-select-class')
  })

  it('honors an isScrollable override on the open menu', async () => {
    render(<TestSynSelect isScrollable={false} />)

    await openMenu()

    expect(getOpenMenu()).not.toHaveClass('pf-m-scrollable')
  })

  it('keeps default maxMenuHeight when caller popperProps are merged', async () => {
    render(<TestSynSelect popperProps={{ position: 'start' }} />)

    await openMenu()

    const menu = getOpenMenu()
    expect(menu).toHaveClass('pf-m-scrollable')
    expect(getMenuContentMaxHeight(menu)).toBe(LONG_SELECT_MAX_MENU_HEIGHT)
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
