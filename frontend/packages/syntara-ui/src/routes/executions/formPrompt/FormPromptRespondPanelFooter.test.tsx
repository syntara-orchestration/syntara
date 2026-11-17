import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import {
  FormPromptRespondPanelFooterOutlet,
  FormPromptRespondPanelFooterProvider,
  FormPromptRespondPanelFooterSlot,
  FormPromptRespondPanelFooterTestHarness,
} from './FormPromptRespondPanelFooter'

describe('FormPromptRespondPanelFooter', () => {
  it('renders footer inline when no panel provider is present', () => {
    render(
      <FormPromptRespondPanelFooterSlot>
        <button type="button">Send</button>
      </FormPromptRespondPanelFooterSlot>
    )

    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
  })

  it('projects footer through the panel provider', () => {
    let captured: ReactNode = null

    render(
      <FormPromptRespondPanelFooterProvider onFooterChange={(footer) => (captured = footer)}>
        <FormPromptRespondPanelFooterSlot>
          <button type="button">Submit response</button>
        </FormPromptRespondPanelFooterSlot>
      </FormPromptRespondPanelFooterProvider>
    )

    expect(screen.queryByRole('button', { name: 'Submit response' })).not.toBeInTheDocument()
    render(<>{captured}</>)
    expect(screen.getByRole('button', { name: 'Submit response' })).toBeInTheDocument()
  })

  it('renders projected footer through the outlet', () => {
    render(
      <FormPromptRespondPanelFooterProvider>
        <FormPromptRespondPanelFooterSlot>
          <button type="button">Submit response</button>
        </FormPromptRespondPanelFooterSlot>
        <FormPromptRespondPanelFooterOutlet />
      </FormPromptRespondPanelFooterProvider>
    )

    expect(screen.getByRole('button', { name: 'Submit response' })).toBeInTheDocument()
  })

  it('notifies onFooterChange when the slot mounts and clears on unmount', () => {
    const onFooterChange = vi.fn()
    const { unmount } = render(
      <FormPromptRespondPanelFooterProvider onFooterChange={onFooterChange}>
        <FormPromptRespondPanelFooterSlot>
          <button type="button">Submit response</button>
        </FormPromptRespondPanelFooterSlot>
      </FormPromptRespondPanelFooterProvider>
    )

    expect(onFooterChange).toHaveBeenCalled()
    expect(onFooterChange.mock.calls.at(-1)?.[0]).not.toBeNull()

    unmount()
    expect(onFooterChange).toHaveBeenLastCalledWith(null)
  })

  it('skips redundant footer updates when the node reference is unchanged', () => {
    const onFooterChange = vi.fn()
    const stableFooter = <button type="button">Stable</button>

    const { rerender } = render(
      <FormPromptRespondPanelFooterProvider onFooterChange={onFooterChange}>
        <FormPromptRespondPanelFooterSlot>{stableFooter}</FormPromptRespondPanelFooterSlot>
      </FormPromptRespondPanelFooterProvider>
    )

    expect(onFooterChange).toHaveBeenCalledTimes(1)

    rerender(
      <FormPromptRespondPanelFooterProvider onFooterChange={onFooterChange}>
        <FormPromptRespondPanelFooterSlot>{stableFooter}</FormPromptRespondPanelFooterSlot>
      </FormPromptRespondPanelFooterProvider>
    )

    expect(onFooterChange).toHaveBeenCalledTimes(1)
  })

  it('renders null from the outlet when no provider is present', () => {
    const { container } = render(<FormPromptRespondPanelFooterOutlet />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders harness footer in the document', () => {
    render(
      <FormPromptRespondPanelFooterTestHarness>
        <FormPromptRespondPanelFooterSlot>
          <button type="button">Send</button>
        </FormPromptRespondPanelFooterSlot>
      </FormPromptRespondPanelFooterTestHarness>
    )

    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
  })

  it('has no accessibility violations for inline footer slot', async () => {
    const { container } = render(
      <FormPromptRespondPanelFooterSlot>
        <button type="button">Send</button>
      </FormPromptRespondPanelFooterSlot>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
