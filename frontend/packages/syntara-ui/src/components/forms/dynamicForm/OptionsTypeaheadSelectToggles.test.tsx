import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { MultiTypeaheadToggle, SingleTypeaheadToggle } from './OptionsTypeaheadSelectToggles'

describe('OptionsTypeaheadSelectToggles', () => {
  it('has no accessibility violations for single-select toggle', async () => {
    const { container } = render(
      <SingleTypeaheadToggle
        toggleRef={() => undefined}
        fieldId="tier"
        ariaLabel="Tier"
        isOpen={false}
        isDisabled={false}
        filterValue=""
        displayValue=""
        placeholder="Select tier"
        onToggle={() => undefined}
        onFilterChange={() => undefined}
        onClearSelection={() => undefined}
        hasSelection={false}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations for single-select toggle when open with a selection', async () => {
    const { container } = render(
      <SingleTypeaheadToggle
        toggleRef={() => undefined}
        fieldId="tier"
        ariaLabel="Tier"
        isOpen
        isDisabled={false}
        filterValue="be"
        displayValue="Beta"
        placeholder="Select tier"
        onToggle={() => undefined}
        onFilterChange={() => undefined}
        onClearSelection={() => undefined}
        hasSelection
      />
    )

    expect(screen.getByRole('button', { name: 'Clear selection' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations for multi-select toggle with chips', async () => {
    const { container } = render(
      <MultiTypeaheadToggle
        toggleRef={() => undefined}
        fieldId="tags"
        ariaLabel="Tags"
        isOpen
        isDisabled={false}
        filterValue="be"
        placeholder="Select options"
        selectedChips={[{ key: 'a', label: 'Alpha', value: 'a' }]}
        onToggle={() => undefined}
        onFilterChange={() => undefined}
        onRemoveSelection={() => undefined}
        onClearAll={() => undefined}
        inputRef={{ current: null }}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
