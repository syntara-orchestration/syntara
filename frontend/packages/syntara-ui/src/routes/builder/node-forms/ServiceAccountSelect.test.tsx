import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { useCanI } from '../../../hooks/useCanI'

import { ServiceAccountSelect } from './ServiceAccountSelect'
import { useAllServiceAccounts } from './useAllServiceAccounts'

vi.mock('./useAllServiceAccounts', () => ({
  useAllServiceAccounts: vi.fn(),
}))

vi.mock('../../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: () => 'project-123',
}))

vi.mock('./CreateServiceAccountInlineModal', () => ({
  CreateServiceAccountInlineModal: ({
    isOpen,
    onClose,
    onCreated,
  }: {
    isOpen: boolean
    onClose: () => void
    onCreated: (id: string) => void
  }) =>
    isOpen ? (
      <div data-testid="create-sa-modal">
        <button onClick={onClose}>Close modal</button>
        <button onClick={() => onCreated('new-sa-id')}>Simulate create</button>
      </div>
    ) : null,
}))

const SA_FIELDS = {
  project_id: 'project-123',
  created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1' },
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  status: 'active' as const,
}

const mockSAs = [
  { id: 'sa-1', name: 'Jenkins SA', description: 'CI integration', ...SA_FIELDS },
  { id: 'sa-2', name: 'EDA SA', description: null, ...SA_FIELDS },
]

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

function setupMocks(overrides?: { resources?: typeof mockSAs; isLoading?: boolean }) {
  const refetch = vi.fn().mockResolvedValue({})
  vi.mocked(useAllServiceAccounts).mockReturnValue({
    serviceAccounts: overrides?.resources ?? mockSAs,
    isLoading: overrides?.isLoading ?? false,
    refetch,
  })
  return { refetch }
}

describe('ServiceAccountSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('renders toggle with placeholder when nothing selected', () => {
    setupMocks()
    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    expect(screen.getByText('Select service accounts')).toBeInTheDocument()
  })

  it('renders toggle showing selected count', () => {
    setupMocks()
    render(<ServiceAccountSelect selectedIds={['sa-1']} onChange={vi.fn()} />, { wrapper })

    expect(screen.getByText('1 selected')).toBeInTheDocument()
  })

  it('shows spinner when loading', () => {
    setupMocks({ isLoading: true })
    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    expect(screen.getByLabelText('Loading service accounts')).toBeInTheDocument()
  })

  it('opens dropdown and shows SA options', async () => {
    setupMocks()
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    await user.click(screen.getByText('Select service accounts'))

    expect(screen.getByText('Jenkins SA')).toBeInTheDocument()
    expect(screen.getByText('EDA SA')).toBeInTheDocument()
  })

  it('shows "Create new service account" option when user has permission', async () => {
    setupMocks()
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    await user.click(screen.getByText('Select service accounts'))

    expect(screen.getByText('Create new service account')).toBeInTheDocument()
  })

  it('calls onChange when selecting an SA', async () => {
    setupMocks()
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={[]} onChange={onChange} />, { wrapper })

    await user.click(screen.getByText('Select service accounts'))
    await user.click(screen.getByText('Jenkins SA'))

    expect(onChange).toHaveBeenCalledWith(['sa-1'])
  })

  it('shows selected SAs as removable labels', () => {
    setupMocks()
    render(<ServiceAccountSelect selectedIds={['sa-1']} onChange={vi.fn()} />, { wrapper })

    expect(screen.getByText('Jenkins SA')).toBeInTheDocument()
  })

  it('removes SA when clicking label close button', async () => {
    setupMocks()
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={['sa-1', 'sa-2']} onChange={onChange} />, { wrapper })

    const closeButtons = screen.getAllByRole('button', { name: /close/i })
    await user.click(closeButtons[0])

    expect(onChange).toHaveBeenCalledWith(['sa-2'])
  })

  it('shows "No service accounts available" when list is empty', async () => {
    setupMocks({ resources: [] })
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    await user.click(screen.getByText('Select service accounts'))

    expect(screen.getByText('No service accounts available')).toBeInTheDocument()
  })

  it('opens create modal when "Create new" is clicked', async () => {
    setupMocks()
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    await user.click(screen.getByText('Select service accounts'))
    await user.click(screen.getByText('Create new service account'))

    expect(screen.getByTestId('create-sa-modal')).toBeInTheDocument()
  })

  it('auto-selects newly created SA and refetches', async () => {
    const { refetch } = setupMocks()
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={[]} onChange={onChange} />, { wrapper })

    await user.click(screen.getByText('Select service accounts'))
    await user.click(screen.getByText('Create new service account'))
    await user.click(screen.getByText('Simulate create'))

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(['new-sa-id'])
      expect(refetch).toHaveBeenCalled()
    })
  })

  it('disables toggle when isDisabled is true', () => {
    setupMocks()
    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} isDisabled />, { wrapper })

    expect(screen.getByRole('button', { name: 'Select service accounts' })).toBeDisabled()
  })

  it('does not show labels when no SAs are selected', () => {
    setupMocks()
    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    expect(screen.queryByLabelText('Selected service accounts')).not.toBeInTheDocument()
  })

  it('shows multiple selected labels', () => {
    setupMocks()
    render(<ServiceAccountSelect selectedIds={['sa-1', 'sa-2']} onChange={vi.fn()} />, { wrapper })

    expect(screen.getByText('2 selected')).toBeInTheDocument()
    expect(screen.getByText('Jenkins SA')).toBeInTheDocument()
    expect(screen.getByText('EDA SA')).toBeInTheDocument()
  })

  it('does not show close on labels when disabled', () => {
    setupMocks()
    render(<ServiceAccountSelect selectedIds={['sa-1']} onChange={vi.fn()} isDisabled />, { wrapper })

    expect(screen.queryByRole('button', { name: /close/i })).not.toBeInTheDocument()
  })

  it('deselects SA when clicking an already-selected option in dropdown', async () => {
    setupMocks()
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={['sa-1', 'sa-2']} onChange={onChange} />, { wrapper })

    await user.click(screen.getByText('2 selected'))

    const jenkinsOptions = screen.getAllByText('Jenkins SA')
    await user.click(jenkinsOptions[jenkinsOptions.length - 1])

    expect(onChange).toHaveBeenCalledWith(['sa-2'])
  })

  it('does not duplicate SA when created SA is already selected', async () => {
    const { refetch } = setupMocks()
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={['sa-1']} onChange={onChange} />, { wrapper })

    await user.click(screen.getByText('1 selected'))
    await user.click(screen.getByText('Create new service account'))
    await user.click(screen.getByText('Simulate create'))

    await waitFor(() => {
      expect(refetch).toHaveBeenCalled()
    })

    expect(onChange).toHaveBeenCalledWith(['sa-1', 'new-sa-id'])
  })

  it('hides "Create new" option when user lacks permission', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    setupMocks()
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    await user.click(screen.getByText('Select service accounts'))

    expect(screen.queryByText('Create new service account')).not.toBeInTheDocument()
  })

  it('passes custom id to toggle', () => {
    setupMocks()
    render(<ServiceAccountSelect id="my-select" selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    expect(screen.getByRole('button', { name: 'Select service accounts' })).toHaveAttribute('id', 'my-select')
  })

  it('does not show "No service accounts" message while still loading', async () => {
    setupMocks({ resources: [], isLoading: true })
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    await user.click(screen.getByLabelText('Loading service accounts'))

    expect(screen.queryByText('No service accounts available')).not.toBeInTheDocument()
  })

  it('shows SA description when available', async () => {
    setupMocks()
    const user = userEvent.setup()

    render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    await user.click(screen.getByText('Select service accounts'))

    expect(screen.getByText('CI integration')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    setupMocks()
    const { container } = render(<ServiceAccountSelect selectedIds={[]} onChange={vi.fn()} />, { wrapper })

    expect(await axe(container)).toHaveNoViolations()
  })
})
