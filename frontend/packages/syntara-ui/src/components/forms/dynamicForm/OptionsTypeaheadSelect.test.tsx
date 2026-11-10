import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { OptionsTypeaheadSelect } from './OptionsTypeaheadSelect'

const sampleOptions = [
  { label: 'Alpha', value: 'a' },
  { label: 'Beta', value: 'b' },
  { label: 'Gamma', value: 'c' },
] as const

const NONE_KEY = '__none__'

function getTypeaheadInput(name: string | RegExp) {
  return screen.getByRole('textbox', { name })
}

describe('OptionsTypeaheadSelect', () => {
  it('filters single-select options as the user types', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <OptionsTypeaheadSelect
        fieldId="tier"
        ariaLabel="Tier"
        options={[...sampleOptions]}
        value=""
        onChange={onChange}
        isMulti={false}
        emptyPlaceholder="Select tier"
      />
    )

    await user.click(getTypeaheadInput('Tier'))
    await user.type(getTypeaheadInput('Tier'), 'be')

    const list = screen.getByRole('listbox', { name: 'Tier' })
    expect(within(list).getByRole('option', { name: 'Beta' })).toBeInTheDocument()
    expect(within(list).queryByRole('option', { name: 'Alpha' })).not.toBeInTheDocument()
  })

  it('selects a filtered option in single-select mode', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <OptionsTypeaheadSelect
        fieldId="tier"
        ariaLabel="Tier"
        options={[...sampleOptions]}
        value=""
        onChange={onChange}
        isMulti={false}
      />
    )

    await user.click(getTypeaheadInput('Tier'))
    await user.type(getTypeaheadInput('Tier'), 'gam')
    await user.click(screen.getByRole('option', { name: 'Gamma' }))

    expect(onChange).toHaveBeenCalledWith('c')
  })

  it('toggles multi-select options while filtering', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <OptionsTypeaheadSelect
        fieldId="tags"
        ariaLabel="Tags"
        options={[...sampleOptions]}
        value={['a']}
        onChange={onChange}
        isMulti
      />
    )

    await user.click(getTypeaheadInput('Tags'))
    await user.type(getTypeaheadInput('Tags'), 'be')
    await user.click(screen.getByRole('checkbox', { name: 'Beta' }))

    expect(onChange).toHaveBeenCalledWith(['a', 'b'])
  })

  it('selects an additional option without changing the primary value', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const onNone = vi.fn()

    render(
      <OptionsTypeaheadSelect
        fieldId="tier"
        ariaLabel="Tier"
        options={[...sampleOptions]}
        value="b"
        onChange={onChange}
        isMulti={false}
        additionalOptions={[{ key: NONE_KEY, label: 'None', isSelected: false, onSelect: onNone }]}
      />
    )

    await user.click(getTypeaheadInput('Tier'))
    await user.click(screen.getByRole('option', { name: 'None' }))

    expect(onNone).toHaveBeenCalledTimes(1)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('disables the typeahead when loadErrorMessage is set', () => {
    render(
      <OptionsTypeaheadSelect
        fieldId="tier"
        ariaLabel="Tier"
        options={[...sampleOptions]}
        value=""
        onChange={vi.fn()}
        isMulti={false}
        loadErrorMessage="Failed to load"
      />
    )

    expect(getTypeaheadInput('Tier')).toBeDisabled()
  })

  it('clears a single selection from the toggle control', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <OptionsTypeaheadSelect
        fieldId="tier"
        ariaLabel="Tier"
        options={[...sampleOptions]}
        value="b"
        onChange={onChange}
        isMulti={false}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Clear selection' }))

    expect(onChange).toHaveBeenCalledWith('')
  })

  it('shows a no-results message when the filter matches nothing', async () => {
    const user = userEvent.setup()

    render(
      <OptionsTypeaheadSelect
        fieldId="tier"
        ariaLabel="Tier"
        options={[...sampleOptions]}
        value=""
        onChange={vi.fn()}
        isMulti={false}
      />
    )

    await user.click(getTypeaheadInput('Tier'))
    await user.type(getTypeaheadInput('Tier'), 'nope')

    expect(screen.getByRole('option', { name: 'No results match "nope"' })).toBeInTheDocument()
  })

  it('has no accessibility violations in default, open, and filtered states', async () => {
    const user = userEvent.setup()

    const { container } = render(
      <OptionsTypeaheadSelect
        fieldId="tier"
        ariaLabel="Tier"
        options={[...sampleOptions]}
        value=""
        onChange={vi.fn()}
        isMulti={false}
        emptyPlaceholder="Select tier"
      />
    )
    expect(await axe(container)).toHaveNoViolations()

    await user.click(getTypeaheadInput('Tier'))
    expect(await axe(container)).toHaveNoViolations()

    await user.type(getTypeaheadInput('Tier'), 'be')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations for multi-select with selections', async () => {
    const { container: multiContainer } = render(
      <OptionsTypeaheadSelect
        fieldId="tags"
        ariaLabel="Tags"
        options={[...sampleOptions]}
        value={['a', 'c']}
        onChange={vi.fn()}
        isMulti
      />
    )
    expect(await axe(multiContainer)).toHaveNoViolations()
  })
})
