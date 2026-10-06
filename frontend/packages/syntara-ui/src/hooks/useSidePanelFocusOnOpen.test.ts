import { renderHook } from '@testing-library/react'
import { createRef } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import { useSidePanelFocusOnOpen } from './useSidePanelFocusOnOpen'

describe('useSidePanelFocusOnOpen', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('focuses the panel close button when opened', () => {
    const panel = document.createElement('div')
    const closeButton = document.createElement('button')
    closeButton.setAttribute('aria-label', 'Close form prompt panel')
    panel.append(closeButton)
    document.body.append(panel)

    const panelRef = createRef<HTMLDivElement>()
    panelRef.current = panel

    const trigger = document.createElement('button')
    trigger.textContent = 'Respond to prompt'
    document.body.append(trigger)
    trigger.focus()

    renderHook(() => useSidePanelFocusOnOpen(true, panelRef))

    expect(closeButton).toHaveFocus()
  })
})
