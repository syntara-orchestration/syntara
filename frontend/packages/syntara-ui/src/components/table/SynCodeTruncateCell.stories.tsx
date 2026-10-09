import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { Meta, StoryObj } from '@storybook/tanstack-react'

import { SynListPanelTable } from '../panels/list/SynListPanel'

import { SynCodeTruncateCell } from './SynCodeTruncateCell'

const LONG_POLICY_NAME = 'builtin-system-administrator-full-access-policy'

const meta: Meta<typeof SynCodeTruncateCell> = {
  component: SynCodeTruncateCell,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Monospace table cell for identifiers such as policy names. Wraps PatternFly `Truncate` inside a width-constrained `<code>` element so overflow detection and the hover tooltip work inside table columns.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** Short content that fits without truncation. */
export const Default: Story = {
  args: {
    content: 'viewer-read-only',
  },
}

/**
 * Narrow column shows ellipsis; hover or focus reveals the full value in a tooltip.
 * Matches access management policy name cells.
 */
export const TruncatedInTable: Story = {
  render: () => (
    <div style={{ maxWidth: '12rem' }}>
      <SynListPanelTable caption="Policy names">
        <Thead>
          <Tr>
            <Th>Name</Th>
          </Tr>
        </Thead>
        <Tbody>
          <Tr>
            <Td dataLabel="Name">
              <SynCodeTruncateCell content={LONG_POLICY_NAME} />
            </Td>
          </Tr>
        </Tbody>
      </SynListPanelTable>
    </div>
  ),
}
