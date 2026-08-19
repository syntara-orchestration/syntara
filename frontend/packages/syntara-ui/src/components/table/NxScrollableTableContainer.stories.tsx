import {
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Label,
  type LabelProps,
  StackItem,
} from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiCloseCircleIcon, RhUiHourglassIcon, RhUiSyncIcon } from '@patternfly/react-icons'
import { ActionsColumn, ExpandableRowContent, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { Decorator, Meta, StoryObj } from '@storybook/react-vite'
import type React from 'react'
import { Fragment, useState } from 'react'

import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'
import { FilterBar } from '../filters/FilterBar'
import { NxPanel } from '../layout/NxPanel'
import { NxPanelContentStack } from '../layout/NxPanelContentStack'

import { NxScrollableTableContainer } from './NxScrollableTableContainer'

type StatusValue = 'completed' | 'failed' | 'running' | 'pending'

type SampleRow = {
  name: string
  status: StatusValue
  createdAt: string
  updatedAt: string
  description: string
  createdBy: string
  lastModifiedBy: string
}

const STATUS_CONFIG: Record<StatusValue, { label: string; status: LabelProps['status']; icon: React.ComponentType }> = {
  completed: { label: 'Completed', status: 'success', icon: RhUiCheckCircleIcon },
  failed: { label: 'Failed', status: 'danger', icon: RhUiCloseCircleIcon },
  running: { label: 'Running', status: 'custom', icon: RhUiSyncIcon },
  pending: { label: 'Pending', status: 'custom', icon: RhUiHourglassIcon },
}

const SAMPLE_ROWS: SampleRow[] = Array.from({ length: 20 }, (_, i) => {
  const statuses: StatusValue[] = ['completed', 'failed', 'running', 'pending']
  const users = ['admin', 'jsmith', 'mgarcia', 'tcheng']
  return {
    name: `resource-${String(i + 1).padStart(2, '0')}`,
    status: statuses[i % statuses.length],
    createdAt: `Jan ${String(i + 1).padStart(2, '0')}, 2026`,
    updatedAt: `Mar ${String(((i * 3) % 28) + 1).padStart(2, '0')}, 2026`,
    description: `Automated pipeline configuration for ${['staging', 'production', 'development', 'testing'][i % 4]} environment`,
    createdBy: users[i % users.length],
    lastModifiedBy: users[(i + 2) % users.length],
  }
})

function StatusLabel({ status }: Readonly<{ status: StatusValue }>) {
  const config = STATUS_CONFIG[status]
  const Icon = config.icon
  return (
    <Label isCompact status={config.status} icon={<Icon />}>
      {config.label}
    </Label>
  )
}

const ROW_ACTIONS = [
  { title: 'Edit', onClick: () => {} },
  { title: 'Delete', onClick: () => {} },
]

const STORY_FILTER_FIELDS = [
  {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by name',
  },
]

/**
 * Mirrors the real app shell that every list page uses:
 *   NxPanel isFullHeight
 *     NxPanelContentStack variant="inset"
 *       StackItem → FilterBar  (static, non-functional)
 *       NxScrollableTableContainer   ← Story renders here
 *
 * The height-constrained outer div simulates NxPageBody giving the panel a
 * bounded height so the table can scroll internally.
 */
const panelDecorator: Decorator = (Story) => (
  <div style={{ height: '500px', display: 'flex', flexDirection: 'column' }}>
    <NxPanel isFullHeight>
      <NxPanelContentStack variant="inset">
        <StackItem>
          <FilterBar fieldDefinitions={STORY_FILTER_FIELDS} filters={[]} onFilterChange={() => {}} showClearAll />
        </StackItem>
        <Story />
      </NxPanelContentStack>
    </NxPanel>
  </div>
)

const meta: Meta<typeof NxScrollableTableContainer> = {
  component: NxScrollableTableContainer,
  tags: ['autodocs'],
  decorators: [panelDecorator],
  parameters: {
    docs: {
      description: {
        component:
          'Scrollable table container with sticky headers and optional pagination.\n\n' +
          '**Layout contract:** The root element is a `StackItem isFilled` — it must be a **direct child** ' +
          'of a `Stack` (typically `NxPanelContentStack`). Wrapping it in another `StackItem` breaks ' +
          'flex layout and the table will not fill the panel height.\n\n' +
          '**Props:**\n' +
          '- `isExpandable` — set when using expandable rows so PatternFly can size columns correctly ' +
          '(disables `table-layout: fixed`).\n' +
          '- `useFixedLayout` — opt out of fixed layout for non-expandable tables (rarely needed).\n' +
          '- `variant` — pass `compact` for dense tables in tight panels (PatternFly table density).\n' +
          '- `isStriped` — alternating row colors (PatternFly `Table` striping).\n' +
          '- `footer` — pass `PaginationFooterProps` to render a `PaginationFooter` below the table.\n' +
          '- `footerContent` — custom footer in the same pinned slot when standard pagination does not fit.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** Basic scrollable table with 20 rows, no pagination footer. */
export const Default: Story = {
  args: {
    caption: 'Resources table',
    children: (
      <>
        <Thead>
          <Tr>
            <Th>Name</Th>
            <Th>Status</Th>
            <Th>Created at</Th>
            <Th>Updated at</Th>
            <Th screenReaderText="Actions" />
          </Tr>
        </Thead>
        <Tbody>
          {SAMPLE_ROWS.map((row) => (
            <Tr key={row.name}>
              <Td dataLabel="Name">{row.name}</Td>
              <Td dataLabel="Status">
                <StatusLabel status={row.status} />
              </Td>
              <Td dataLabel="Created at">{row.createdAt}</Td>
              <Td dataLabel="Updated at">{row.updatedAt}</Td>
              <Td isActionCell>
                <ActionsColumn items={ROW_ACTIONS} />
              </Td>
            </Tr>
          ))}
        </Tbody>
      </>
    ),
  },
}

/** Table with only a few rows — no overflow, so no bottom fade gradient. */
export const FewRows: Story = {
  args: {
    caption: 'Short resources table',
    children: (
      <>
        <Thead>
          <Tr>
            <Th>Name</Th>
            <Th>Status</Th>
            <Th>Created at</Th>
            <Th>Updated at</Th>
            <Th screenReaderText="Actions" />
          </Tr>
        </Thead>
        <Tbody>
          {SAMPLE_ROWS.slice(0, 3).map((row) => (
            <Tr key={row.name}>
              <Td dataLabel="Name">{row.name}</Td>
              <Td dataLabel="Status">
                <StatusLabel status={row.status} />
              </Td>
              <Td dataLabel="Created at">{row.createdAt}</Td>
              <Td dataLabel="Updated at">{row.updatedAt}</Td>
              <Td isActionCell>
                <ActionsColumn items={ROW_ACTIONS} />
              </Td>
            </Tr>
          ))}
        </Tbody>
      </>
    ),
  },
}

/** Table with interactive cursor-style pagination. */
export const WithPagination: Story = {
  render: function WithPaginationStory() {
    const [page, setPage] = useState(1)
    const [perPage, setPerPage] = useState(10)

    const start = (page - 1) * perPage
    const pageRows = SAMPLE_ROWS.slice(start, start + perPage)
    const hasNext = start + perPage < SAMPLE_ROWS.length

    return (
      <NxScrollableTableContainer
        caption="Paginated resources table"
        footer={{
          page,
          perPage,
          total: SAMPLE_ROWS.length,
          hasNext,
          onPrev: () => setPage((p) => Math.max(1, p - 1)),
          onNext: () => setPage((p) => p + 1),
          onPerPageChange: (newPerPage) => {
            setPerPage(newPerPage)
            setPage(1)
          },
        }}
      >
        <Thead>
          <Tr>
            <Th>Name</Th>
            <Th>Status</Th>
            <Th>Created at</Th>
            <Th>Updated at</Th>
            <Th screenReaderText="Actions" />
          </Tr>
        </Thead>
        <Tbody>
          {pageRows.map((row) => (
            <Tr key={row.name}>
              <Td dataLabel="Name">{row.name}</Td>
              <Td dataLabel="Status">
                <StatusLabel status={row.status} />
              </Td>
              <Td dataLabel="Created at">{row.createdAt}</Td>
              <Td dataLabel="Updated at">{row.updatedAt}</Td>
              <Td isActionCell>
                <ActionsColumn items={ROW_ACTIONS} />
              </Td>
            </Tr>
          ))}
        </Tbody>
      </NxScrollableTableContainer>
    )
  },
}

/** Expandable table with detail lists in expanded rows and interactive pagination. */
export const Expandable: Story = {
  render: function ExpandableStory() {
    const [page, setPage] = useState(1)
    const [perPage, setPerPage] = useState(10)
    const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

    const start = (page - 1) * perPage
    const pageRows = SAMPLE_ROWS.slice(start, start + perPage)
    const hasNext = start + perPage < SAMPLE_ROWS.length

    const isAllExpanded = pageRows.length > 0 && pageRows.every((row) => expandedRows.has(row.name))

    function toggleRow(name: string) {
      setExpandedRows((prev) => {
        const next = new Set(prev)
        if (next.has(name)) {
          next.delete(name)
        } else {
          next.add(name)
        }
        return next
      })
    }

    function toggleAll() {
      if (isAllExpanded) {
        setExpandedRows(new Set())
      } else {
        setExpandedRows(new Set(pageRows.map((row) => row.name)))
      }
    }

    const columnCount = 6

    return (
      <NxScrollableTableContainer
        caption="Expandable resources table"
        isExpandable
        footer={{
          page,
          perPage,
          total: SAMPLE_ROWS.length,
          hasNext,
          onPrev: () => setPage((p) => Math.max(1, p - 1)),
          onNext: () => setPage((p) => p + 1),
          onPerPageChange: (newPerPage) => {
            setPerPage(newPerPage)
            setPage(1)
          },
        }}
      >
        <Thead>
          <Tr>
            <Th
              expand={{
                areAllExpanded: isAllExpanded,
                onToggle: toggleAll,
                collapseAllAriaLabel: isAllExpanded ? 'Collapse all rows' : 'Expand all rows',
              }}
              aria-label="Row expansion"
            />
            <Th>Name</Th>
            <Th>Status</Th>
            <Th>Created at</Th>
            <Th>Updated at</Th>
            <Th screenReaderText="Actions" />
          </Tr>
        </Thead>
        <Tbody>
          {pageRows.map((row, rowIndex) => {
            const isExpanded = expandedRows.has(row.name)
            return (
              <Fragment key={row.name}>
                <Tr>
                  <Td
                    expand={{
                      rowIndex,
                      isExpanded,
                      onToggle: () => toggleRow(row.name),
                      expandId: `expand-${row.name}`,
                    }}
                  />
                  <Td dataLabel="Name">{row.name}</Td>
                  <Td dataLabel="Status">
                    <StatusLabel status={row.status} />
                  </Td>
                  <Td dataLabel="Created at">{row.createdAt}</Td>
                  <Td dataLabel="Updated at">{row.updatedAt}</Td>
                  <Td isActionCell>
                    <ActionsColumn items={ROW_ACTIONS} />
                  </Td>
                </Tr>
                <Tr isExpanded={isExpanded}>
                  <Td colSpan={columnCount}>
                    <ExpandableRowContent>
                      <DescriptionList isCompact isHorizontal>
                        <DescriptionListGroup>
                          <DescriptionListTerm>Description</DescriptionListTerm>
                          <DescriptionListDescription>{row.description}</DescriptionListDescription>
                        </DescriptionListGroup>
                        <DescriptionListGroup>
                          <DescriptionListTerm>Created by</DescriptionListTerm>
                          <DescriptionListDescription>{row.createdBy}</DescriptionListDescription>
                        </DescriptionListGroup>
                        <DescriptionListGroup>
                          <DescriptionListTerm>Last modified by</DescriptionListTerm>
                          <DescriptionListDescription>{row.lastModifiedBy}</DescriptionListDescription>
                        </DescriptionListGroup>
                      </DescriptionList>
                    </ExpandableRowContent>
                  </Td>
                </Tr>
              </Fragment>
            )
          })}
        </Tbody>
      </NxScrollableTableContainer>
    )
  },
}
