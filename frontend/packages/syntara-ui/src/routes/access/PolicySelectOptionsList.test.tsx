import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { PolicySelectOptionsList } from './PolicySelectOptionsList'

describe('PolicySelectOptionsList', () => {
  const options = [
    { name: 'workflow-admin', description: 'Manage workflows' },
    { name: 'project-viewer', description: null },
  ]

  it('has no accessibility violations when options are available', async () => {
    const { container } = render(
      <PolicySelectOptionsList
        isLoading={false}
        filterValue=""
        filteredOptions={options}
        selected={['workflow-admin']}
        isSelectingAll={false}
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations while loading', async () => {
    const { container } = render(
      <PolicySelectOptionsList isLoading filterValue="" filteredOptions={[]} selected={[]} isSelectingAll={false} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders Select All when options exist', () => {
    render(
      <PolicySelectOptionsList
        isLoading={false}
        filterValue=""
        filteredOptions={options}
        selected={[]}
        isSelectingAll={false}
      />
    )

    expect(screen.getByRole('menuitem', { name: 'Select all' })).toBeInTheDocument()
  })

  it('disables Select All and shows progress while selection is in progress', () => {
    render(
      <PolicySelectOptionsList
        isLoading={false}
        filterValue=""
        filteredOptions={options}
        selected={[]}
        isSelectingAll
      />
    )

    expect(screen.getByRole('menuitem', { name: /Selecting all/i })).toBeDisabled()
  })
})
