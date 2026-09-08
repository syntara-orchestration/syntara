import { Stack, StackItem } from '@patternfly/react-core'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynScrollableTableContainer } from './SynScrollableTableContainer'

describe('SynScrollableTableContainer', () => {
  const minimalTable = (
    <>
      <Thead>
        <Tr>
          <Th>Column A</Th>
        </Tr>
      </Thead>
      <Tbody>
        <Tr>
          <Td>Value</Td>
        </Tr>
      </Tbody>
    </>
  )

  it('renders table content when used as a direct child of Stack', () => {
    render(
      <Stack style={{ height: '240px' }}>
        <SynScrollableTableContainer caption="Demo table">{minimalTable}</SynScrollableTableContainer>
      </Stack>
    )

    expect(screen.getByRole('grid')).toBeInTheDocument()
  })

  it('scroll container is a named region landmark with tabIndex 0 for keyboard scrolling', () => {
    render(
      <Stack style={{ height: '240px' }}>
        <SynScrollableTableContainer caption="Demo table">{minimalTable}</SynScrollableTableContainer>
      </Stack>
    )

    const region = screen.getByRole('region', { name: 'Demo table' })
    expect(region).toHaveAttribute('tabindex', '0')
  })

  it('uses default density when variant is omitted', () => {
    render(
      <Stack style={{ height: '240px' }}>
        <SynScrollableTableContainer caption="Demo table">{minimalTable}</SynScrollableTableContainer>
      </Stack>
    )

    expect(screen.getByRole('grid')).not.toHaveClass('pf-m-compact')
  })

  it('applies compact density when variant is compact', () => {
    render(
      <Stack style={{ height: '240px' }}>
        <SynScrollableTableContainer caption="Demo table" variant="compact">
          {minimalTable}
        </SynScrollableTableContainer>
      </Stack>
    )

    expect(screen.getByRole('grid')).toHaveClass('pf-m-compact')
  })

  it('does not stripe rows when isStriped is omitted', () => {
    render(
      <Stack style={{ height: '240px' }}>
        <SynScrollableTableContainer caption="Demo table">{minimalTable}</SynScrollableTableContainer>
      </Stack>
    )

    expect(screen.getByRole('grid')).not.toHaveClass('pf-m-striped')
  })

  it('applies striped rows when isStriped is set', () => {
    render(
      <Stack style={{ height: '240px' }}>
        <SynScrollableTableContainer caption="Demo table" isStriped>
          {minimalTable}
        </SynScrollableTableContainer>
      </Stack>
    )

    expect(screen.getByRole('grid')).toHaveClass('pf-m-striped')
  })

  it('pins custom footerContent inside the container root', () => {
    render(
      <Stack style={{ height: '240px' }}>
        <SynScrollableTableContainer caption="Demo table" footerContent={<p>Custom footer</p>}>
          {minimalTable}
        </SynScrollableTableContainer>
      </Stack>
    )

    const stcRoot = screen.getByTestId('scrollable-table-container-root')
    expect(within(stcRoot).getByText('Custom footer')).toBeInTheDocument()
  })

  it('has no accessibility violations in the supported Stack layout', async () => {
    const { container } = render(
      <Stack style={{ height: '240px' }}>
        <SynScrollableTableContainer caption="Accessible table">{minimalTable}</SynScrollableTableContainer>
      </Stack>
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  /**
   * The component's root is a `StackItem` with `data-testid="scrollable-table-container-root"`. It must
   * be a direct child of the page `Stack` (see `SynScrollableTableContainer` JSDoc). Nesting it inside
   * another `StackItem` breaks flex height.
   */
  it('root is a direct child of the page Stack in the supported layout', () => {
    render(
      <Stack aria-label="Fixture page stack" role="region" style={{ height: '240px' }}>
        <SynScrollableTableContainer caption="Layout table">{minimalTable}</SynScrollableTableContainer>
      </Stack>
    )

    const pageStack = screen.getByRole('region', { name: 'Fixture page stack' })
    const stcRoot = screen.getByTestId('scrollable-table-container-root')
    /* eslint-disable testing-library/no-node-access -- parent link is the structural contract; STC root is not a role. */
    expect(stcRoot.parentElement).toBe(pageStack)
    /* eslint-enable testing-library/no-node-access */
    expect(within(stcRoot).getByRole('grid')).toBeInTheDocument()
  })

  it('is not a direct child of the page Stack when wrapped in an extra StackItem (invalid nesting)', () => {
    render(
      <Stack aria-label="Fixture page stack" role="region" style={{ height: '240px' }}>
        <StackItem isFilled>
          <SynScrollableTableContainer caption="Nested layout table">{minimalTable}</SynScrollableTableContainer>
        </StackItem>
      </Stack>
    )

    const pageStack = screen.getByRole('region', { name: 'Fixture page stack' })
    const stcRoot = screen.getByTestId('scrollable-table-container-root')
    /* eslint-disable testing-library/no-node-access */
    expect(stcRoot.parentElement).not.toBe(pageStack)
    /* eslint-enable testing-library/no-node-access */
    expect(within(stcRoot).getByRole('grid')).toBeInTheDocument()
  })
})
