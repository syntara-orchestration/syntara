import type { WorkflowAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { VersionHistoryPanel } from './VersionHistoryPanel'
import type { VersionStatus } from './VersionStatusBadge'

vi.mock('../../components/table/PaginationFooter', () => ({
  PaginationFooter: ({ total, perPage }: { total: number; perPage: number }) => (
    <div data-testid="pagination-footer">{`1 - ${perPage} of ${total}`}</div>
  ),
}))

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']

function createMockVersion(overrides: Record<string, unknown> = {}): WorkflowVersion {
  return {
    id: `ver-${(overrides.version as number) ?? 1}`,
    workflow_id: 'wf-1',
    version: 1,
    schema_version: '2.0.0',
    workflow_definition: { schema_version: '2.0.0' as const, name: 'test', triggers: [], nodes: [], edges: [] },
    created_by: 'user-1',
    created_by_username: 'testuser',
    created_at: '2026-05-19T21:59:00.000Z',
    updated_at: '2026-05-19T21:59:00.000Z',
    change_description: 'Initial version',
    status: 'draft',
    name: null,
    ...overrides,
  } as unknown as WorkflowVersion
}

const defaultProps = {
  versions: [
    createMockVersion({
      version: 3,
      status: 'draft',
      created_at: '2026-05-19T21:59:00.000Z',
      change_description: 'Latest changes',
      created_by_username: 'sarah.chen',
    }),
    createMockVersion({
      version: 2,
      status: 'previously_published',
      created_at: '2026-05-16T21:59:00.000Z',
      change_description: 'Published release',
      created_by_username: 'marcus.williams',
    }),
    createMockVersion({
      version: 1,
      status: 'published',
      created_at: '2026-05-12T21:59:00.000Z',
      change_description: 'Initial version',
      created_by_username: 'priya.patel',
    }),
  ],
  onClose: vi.fn(),
  onSelectVersion: vi.fn(),
  onRestoreVersion: vi.fn(),
  onExportVersion: vi.fn(),
  onOpenInNewWindow: vi.fn(),
  onPublishVersion: vi.fn(),
  onViewRunHistory: vi.fn(),
  executedVersionNumbers: new Map([
    [3, 'ver-3'],
    [2, 'ver-2'],
    [1, 'ver-1'],
  ]),
  onEditVersion: vi.fn(),
  onDuplicateVersion: vi.fn(),
  statusFilter: [] as VersionStatus[],
  onStatusFilterChange: vi.fn(),
}

describe('VersionHistoryPanel', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders the panel with title and subtitle', () => {
    render(<VersionHistoryPanel {...defaultProps} />)

    expect(screen.getByText('Version history')).toBeInTheDocument()
    expect(screen.getByText('Browse past saves and publishes.')).toBeInTheDocument()
  })

  it('renders version entries with timestamps and descriptions', () => {
    render(<VersionHistoryPanel {...defaultProps} />)

    expect(screen.getByText('sarah.chen')).toBeInTheDocument()
    expect(screen.getByText('marcus.williams')).toBeInTheDocument()
    expect(screen.getByText('priya.patel')).toBeInTheDocument()
  })

  it('renders status badges for published and previously published versions only', () => {
    render(<VersionHistoryPanel {...defaultProps} />)

    expect(screen.queryByText('Draft')).not.toBeInTheDocument()
    expect(screen.getByText('Previously published')).toBeInTheDocument()
    expect(screen.getByText('Published')).toBeInTheDocument()
  })

  it('calls onClose when close button is clicked', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: 'Collapse version history' }))

    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
  })

  it('shows empty state when no versions and filter is active', () => {
    render(<VersionHistoryPanel {...defaultProps} versions={[]} statusFilter={['published']} />)

    expect(screen.getByRole('button', { name: /clear all filters/i })).toBeInTheDocument()
  })

  it('shows empty message when no versions and no filter', () => {
    render(<VersionHistoryPanel {...defaultProps} versions={[]} />)

    expect(screen.getByText('No version history available')).toBeInTheDocument()
  })

  it('calls onSelectVersion when a version row is clicked', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const listButtons = screen
      .getAllByRole('button')
      .filter((el) => el.classList.contains('pf-v6-c-simple-list__item-link'))
    await user.click(listButtons[0])

    expect(defaultProps.onSelectVersion).toHaveBeenCalledWith(3)
  })

  it('calls onRestoreVersion via kebab menu', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])
    await user.click(screen.getByText('Restore version'))

    expect(defaultProps.onRestoreVersion).toHaveBeenCalledWith(3, '2026-05-19T21:59:00.000Z')
  })

  it('calls onExportVersion via kebab menu', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])
    await user.click(screen.getByText('Export workflow'))

    expect(defaultProps.onExportVersion).toHaveBeenCalledWith(3)
  })

  it('calls onOpenInNewWindow via kebab menu', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])
    await user.click(screen.getByText('Open version in new window'))

    expect(defaultProps.onOpenInNewWindow).toHaveBeenCalledWith(3)
  })

  it('kebab actions do not trigger version row selection', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])
    await user.click(screen.getByText('Open version in new window'))

    expect(defaultProps.onOpenInNewWindow).toHaveBeenCalledWith(3)
    expect(defaultProps.onSelectVersion).not.toHaveBeenCalled()
  })

  it('calls onPublishVersion via kebab menu', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])
    await user.click(screen.getByText('Publish this version'))

    expect(defaultProps.onPublishVersion).toHaveBeenCalledWith(3)
  })

  it('calls onViewRunHistory via kebab menu', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])
    await user.click(screen.getByText('View run history of this version'))

    expect(defaultProps.onViewRunHistory).toHaveBeenCalledWith(defaultProps.versions[0].version)
  })

  it('calls onEditVersion via kebab menu', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])
    await user.click(screen.getByText('Edit version name and description'))

    expect(defaultProps.onEditVersion).toHaveBeenCalledWith(defaultProps.versions[0])
  })

  it('calls onDuplicateVersion via kebab menu', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])
    await user.click(screen.getByText('Duplicate as new workflow'))

    expect(defaultProps.onDuplicateVersion).toHaveBeenCalledWith(defaultProps.versions[0])
  })

  it('renders the status filter', () => {
    render(<VersionHistoryPanel {...defaultProps} />)

    expect(screen.getByText('Filter by state')).toBeInTheDocument()
  })

  it('calls onStatusFilterChange when a filter option is selected', async () => {
    const onStatusFilterChange = vi.fn()
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} onStatusFilterChange={onStatusFilterChange} />)

    await user.click(screen.getByText('Filter by state'))
    const checkbox = screen.getByRole('checkbox', { name: 'Published' })
    await user.click(checkbox)

    expect(onStatusFilterChange).toHaveBeenCalledWith(['published'])
  })

  it('shows Previously published as a filter option', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    await user.click(screen.getByText('Filter by state'))

    expect(screen.getByRole('checkbox', { name: 'Previously published' })).toBeInTheDocument()
  })

  it('renders publish name with secondary datetime under the title', () => {
    const version = createMockVersion({
      version: 4,
      name: 'Release 1.0',
      status: 'published',
      created_at: '2026-05-19T21:59:00.000Z',
      created_by_username: 'sarah.chen',
    })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.getByText('Release 1.0')).toBeInTheDocument()
    expect(screen.getAllByText(/May 19, 2026/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('sarah.chen')).toBeInTheDocument()
    expect(screen.getByText('Published')).toBeInTheDocument()
  })

  it('renders publish name without secondary datetime when created_at is missing', () => {
    const version = createMockVersion({
      version: 4,
      name: 'Named only',
      created_at: null,
      status: 'published',
    })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.getByText('Named only')).toBeInTheDocument()
    expect(screen.queryByText(/May /)).not.toBeInTheDocument()
  })

  it('places username above the status badge in the row', () => {
    const version = createMockVersion({
      version: 2,
      status: 'previously_published',
      created_by_username: 'marcus.williams',
    })
    const { container } = render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.getByText('marcus.williams')).toBeInTheDocument()
    expect(screen.getByText('Previously published')).toBeInTheDocument()
    const rowText = container.textContent ?? ''
    expect(rowText.indexOf('marcus.williams')).toBeLessThan(rowText.indexOf('Previously published'))
  })

  it('filters to published when currently published name is clicked', async () => {
    const onStatusFilterChange = vi.fn()
    const user = userEvent.setup()
    render(
      <VersionHistoryPanel
        {...defaultProps}
        publishedVersionName="Release 1.0"
        onStatusFilterChange={onStatusFilterChange}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Release 1.0' }))

    expect(onStatusFilterChange).toHaveBeenCalledWith(['published'])
  })

  it('shows change descriptions in version rows', () => {
    render(<VersionHistoryPanel {...defaultProps} />)

    expect(screen.getByText('sarah.chen')).toBeInTheDocument()
    expect(screen.getByText('marcus.williams')).toBeInTheDocument()
  })

  it('renders version row without created_at', () => {
    const version = createMockVersion({ version: 5, created_at: null })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.getByText('testuser')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Actions for version/ })).toBeInTheDocument()
  })

  it('renders version row without change_description', () => {
    const version = createMockVersion({ version: 5, change_description: null, created_by_username: null })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.queryByText('testuser')).not.toBeInTheDocument()
    expect(screen.queryByText('Draft')).not.toBeInTheDocument()
  })

  it('renders version row without status', () => {
    const version = createMockVersion({ version: 5, status: null })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.queryByText('Draft')).not.toBeInTheDocument()
    expect(screen.getByText('testuser')).toBeInTheDocument()
  })

  it('renders version row with no optional fields at all', () => {
    const version = createMockVersion({
      version: 5,
      created_at: null,
      change_description: null,
      status: null,
      created_by_username: 'testuser',
    })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.getByRole('button', { name: /Actions for version/ })).toBeInTheDocument()
  })

  it('highlights the selected version and does not highlight others', () => {
    render(<VersionHistoryPanel {...defaultProps} selectedVersion={2} />)

    expect(screen.getByText('marcus.williams')).toBeInTheDocument()
    expect(screen.getByText('sarah.chen')).toBeInTheDocument()
  })

  it('does not highlight any version when selectedVersion is null', () => {
    render(<VersionHistoryPanel {...defaultProps} selectedVersion={null} />)

    expect(screen.getByText('sarah.chen')).toBeInTheDocument()
  })

  it('hides filter when no versions and no filter active', () => {
    render(<VersionHistoryPanel {...defaultProps} versions={[]} statusFilter={[]} />)

    expect(screen.queryByText('Filter by state')).not.toBeInTheDocument()
  })

  it('shows filter when versions exist even with no active filter', () => {
    render(<VersionHistoryPanel {...defaultProps} statusFilter={[]} />)

    expect(screen.getByText('Filter by state')).toBeInTheDocument()
  })

  it('shows filter when statusFilter is active even with no versions', () => {
    render(<VersionHistoryPanel {...defaultProps} versions={[]} statusFilter={['draft']} />)

    expect(screen.getByText('Filter by state')).toBeInTheDocument()
  })

  it('clears filters via empty state clear button', async () => {
    const user = userEvent.setup()
    const onStatusFilterChange = vi.fn()
    render(
      <VersionHistoryPanel
        {...defaultProps}
        versions={[]}
        statusFilter={['published']}
        onStatusFilterChange={onStatusFilterChange}
      />
    )

    await user.click(screen.getByRole('button', { name: /clear all filters/i }))

    expect(onStatusFilterChange).toHaveBeenCalledWith([])
  })

  it('groups versions by date', () => {
    const versions = [
      createMockVersion({
        version: 3,
        created_at: '2026-05-19T10:00:00.000Z',
        change_description: 'v3',
        created_by_username: 'user-v3',
      }),
      createMockVersion({ version: 2, created_at: '2026-05-19T08:00:00.000Z', created_by_username: 'user-v2' }),
      createMockVersion({ version: 1, created_at: '2026-01-15T10:00:00.000Z', created_by_username: 'user-v1' }),
    ]
    render(<VersionHistoryPanel {...defaultProps} versions={versions} />)

    expect(screen.getByText('user-v3')).toBeInTheDocument()
    expect(screen.getByText('user-v2')).toBeInTheDocument()
    expect(screen.getByText('user-v1')).toBeInTheDocument()
  })

  it('handles version with empty string created_at as Unknown group', () => {
    const version = createMockVersion({ version: 5, created_at: '' })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.getByText('testuser')).toBeInTheDocument()
  })

  it('renders version with only created_at field', () => {
    const version = createMockVersion({
      version: 6,
      change_description: null,
      status: null,
      created_by_username: 'testuser',
    })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.getByRole('button', { name: /Actions for version/ })).toBeInTheDocument()
  })

  it('renders version with only username field', () => {
    const version = createMockVersion({ version: 6, created_at: null, status: null })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.getByText('testuser')).toBeInTheDocument()
  })

  it('renders version with only status field', () => {
    const version = createMockVersion({
      version: 6,
      created_at: null,
      change_description: null,
      status: 'published',
      created_by_username: 'testuser',
    })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.getByText('Published')).toBeInTheDocument()
  })

  it('renders multiple versions in different date groups', () => {
    const versions = [
      createMockVersion({ version: 3, created_at: '2026-05-19T10:00:00.000Z', created_by_username: 'recent-user' }),
      createMockVersion({ version: 2, created_at: '2026-01-10T10:00:00.000Z', created_by_username: 'old-user' }),
    ]
    render(<VersionHistoryPanel {...defaultProps} versions={versions} />)

    expect(screen.getByText('recent-user')).toBeInTheDocument()
    expect(screen.getByText('old-user')).toBeInTheDocument()
  })

  it('calls onSelectVersion with correct version number for non-first version', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const listButtons = screen
      .getAllByRole('button')
      .filter((el) => el.classList.contains('pf-v6-c-simple-list__item-link'))
    await user.click(listButtons[listButtons.length - 1])

    expect(defaultProps.onSelectVersion).toHaveBeenCalledWith(1)
  })

  it('calls onRestoreVersion for non-first version via kebab', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[2])
    await user.click(screen.getByText('Restore version'))

    expect(defaultProps.onRestoreVersion).toHaveBeenCalledWith(1, '2026-05-12T21:59:00.000Z')
  })

  it('calls onExportVersion for non-first version via kebab', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[1])
    await user.click(screen.getByText('Export workflow'))

    expect(defaultProps.onExportVersion).toHaveBeenCalledWith(2)
  })

  it('calls onPublishVersion for non-published version via kebab', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])
    await user.click(screen.getByText('Publish this version'))

    expect(defaultProps.onPublishVersion).toHaveBeenCalledWith(3)
  })

  it('disables "View run history" when version has no runs', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} executedVersionNumbers={new Map()} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])

    const viewRunHistoryBtn = screen.getByRole('menuitem', { name: /View run history of this version/ })
    expect(viewRunHistoryBtn).toHaveAttribute('aria-disabled', 'true')
  })

  it('enables "View run history" when version has runs', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])

    const viewRunHistoryBtn = screen.getByRole('menuitem', { name: /View run history of this version/ })
    expect(viewRunHistoryBtn).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('disables publish for already-published version', async () => {
    const user = userEvent.setup()
    render(<VersionHistoryPanel {...defaultProps} />)

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[2])

    const publishBtn = screen.getByRole('menuitem', { name: /Publish this version/ })
    expect(publishBtn).toHaveAttribute('aria-disabled', 'true')
  })

  it('shows name as primary text when set', () => {
    const version = createMockVersion({
      version: 1,
      name: 'Release 1.0',
      created_at: '2026-05-19T10:00:00.000Z',
      created_by_username: 'testuser',
    })
    render(<VersionHistoryPanel {...defaultProps} versions={[version]} />)

    expect(screen.getByText('Release 1.0')).toBeInTheDocument()
  })

  it('disables restore, edit, and duplicate when canEdit is false', async () => {
    const user = userEvent.setup()
    render(
      <VersionHistoryPanel
        {...defaultProps}
        versions={[createMockVersion({ version: 1, status: 'draft', created_by_username: 'user1' })]}
        canEdit={false}
        editTooltip="You do not have permission"
      />
    )

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])

    expect(screen.getByRole('menuitem', { name: /Restore version/ })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('menuitem', { name: /Edit version name/ })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('menuitem', { name: /Duplicate as new/ })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('menuitem', { name: /Publish this version/ })).toHaveAttribute('aria-disabled', 'true')
  })

  it('does not disable export and open in new window when canEdit is false', async () => {
    const user = userEvent.setup()
    render(
      <VersionHistoryPanel
        {...defaultProps}
        versions={[createMockVersion({ version: 1, status: 'draft', created_by_username: 'user1' })]}
        canEdit={false}
      />
    )

    const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
    await user.click(kebabButtons[0])

    expect(screen.getByRole('menuitem', { name: /Export workflow/ })).not.toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('menuitem', { name: /Open version in new window/ })).not.toHaveAttribute(
      'aria-disabled',
      'true'
    )
  })

  describe('pagination', () => {
    const mockOnPrev = vi.fn()
    const mockOnNext = vi.fn()
    const mockOnPerPageChange = vi.fn()

    it('renders pagination footer when paginationFooterProps is provided', () => {
      const paginationFooterProps = {
        page: 1,
        perPage: 20,
        total: 50,
        hasNext: true,
        onPrev: mockOnPrev,
        onNext: mockOnNext,
        onPerPageChange: mockOnPerPageChange,
      }

      render(<VersionHistoryPanel {...defaultProps} paginationFooterProps={paginationFooterProps} />)

      expect(screen.getByTestId('pagination-footer')).toBeInTheDocument()
      expect(screen.getByText('1 - 20 of 50')).toBeInTheDocument()
    })

    it('does not render pagination footer when paginationFooterProps is not provided', () => {
      render(<VersionHistoryPanel {...defaultProps} />)
      expect(screen.queryByTestId('pagination-footer')).not.toBeInTheDocument()
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<VersionHistoryPanel {...defaultProps} versions={[]} />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
