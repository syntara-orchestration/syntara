import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { ExpandableListTableColGroup } from './ExpandableListTableColGroup'

describe('ExpandableListTableColGroup', () => {
  it('renders expand plus data columns', () => {
    const { container } = render(
      <table>
        <ExpandableListTableColGroup dataColumnCount={3} />
      </table>
    )

    // <col> elements are not exposed via Testing Library roles; assert layout structure.
    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access -- colgroup layout
    const cols = container.querySelectorAll('col')
    expect(cols).toHaveLength(4)
  })

  it('renders select, expand, and data columns when withSelect is set', () => {
    const { container } = render(
      <table>
        <ExpandableListTableColGroup withSelect dataColumnCount={2} />
      </table>
    )

    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access -- colgroup layout
    const cols = container.querySelectorAll('col')
    expect(cols).toHaveLength(4)
  })

  it('renders only the expand column when there are zero data columns', () => {
    const { container } = render(
      <table>
        <ExpandableListTableColGroup dataColumnCount={0} />
      </table>
    )

    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access -- colgroup layout
    expect(container.querySelectorAll('col')).toHaveLength(1)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <table>
        <ExpandableListTableColGroup dataColumnCount={1} />
      </table>
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
