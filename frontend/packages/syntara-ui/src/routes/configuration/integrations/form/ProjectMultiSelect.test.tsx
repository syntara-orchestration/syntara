import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ProjectMultiSelect } from './ProjectMultiSelect'

vi.mock('../../../access/useAllProjects', () => ({
  useSelectableProjects: vi.fn(() => ({ projects: [], isLoading: false, error: null, refetch: vi.fn() })),
}))

const { useSelectableProjects } = await import('../../../access/useAllProjects')

const mockProjects = [
  { id: 'proj-1', name: 'Alpha Project' },
  { id: 'proj-2', name: 'Beta Project' },
  { id: 'proj-3', name: 'Gamma Project' },
]

function mockProjectsLoaded(projects = mockProjects) {
  vi.mocked(useSelectableProjects).mockReturnValue({
    projects: projects,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })
}

function mockProjectsLoading() {
  vi.mocked(useSelectableProjects).mockReturnValue({
    projects: [] as ReturnType<typeof useSelectableProjects>['projects'],
    isLoading: true,
    error: null,
    refetch: vi.fn(),
  })
}

describe('ProjectMultiSelect', () => {
  describe('rendering', () => {
    it('renders placeholder when no projects are selected', () => {
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={[]} onChange={vi.fn()} />)

      expect(screen.getByPlaceholderText('Select projects...')).toBeInTheDocument()
    })

    it('renders selected projects as filled blue label chips', () => {
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={['proj-1', 'proj-2']} onChange={vi.fn()} />)

      expect(screen.getByText('Alpha Project', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
      expect(screen.getByText('Beta Project', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
    })

    it('shows clear all button when projects are selected', () => {
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={['proj-1']} onChange={vi.fn()} />)

      expect(screen.getByRole('button', { name: 'Clear all' })).toBeInTheDocument()
    })

    it('hides clear all button when nothing is selected', () => {
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={[]} onChange={vi.fn()} />)

      expect(screen.queryByRole('button', { name: 'Clear all' })).not.toBeInTheDocument()
    })
  })

  describe('dropdown interaction', () => {
    it('opens dropdown and shows options with checkboxes', async () => {
      const user = userEvent.setup()
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={[]} onChange={vi.fn()} />)

      await user.click(screen.getByPlaceholderText('Select projects...'))

      expect(screen.getByText('Alpha Project')).toBeInTheDocument()
      expect(screen.getByText('Beta Project')).toBeInTheDocument()
      expect(screen.getByText('Gamma Project')).toBeInTheDocument()
    })

    it('calls onChange with project added when option is clicked', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={[]} onChange={onChange} />)

      await user.click(screen.getByPlaceholderText('Select projects...'))
      await user.click(screen.getByText('Beta Project'))

      expect(onChange).toHaveBeenCalledWith(['proj-2'])
    })

    it('calls onChange with project removed when checked option is clicked', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={['proj-1', 'proj-2']} onChange={onChange} />)

      await user.click(screen.getByRole('textbox'))
      await user.click(screen.getAllByText('Alpha Project')[1])

      expect(onChange).toHaveBeenCalledWith(['proj-2'])
    })
  })

  describe('removing projects', () => {
    it('removes project when chip close button is clicked', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={['proj-1', 'proj-2']} onChange={onChange} />)

      const closeButtons = screen.getAllByRole('button', { name: /close/i })
      await user.click(closeButtons[0])

      expect(onChange).toHaveBeenCalledWith(['proj-2'])
    })

    it('clears all when clear all button is clicked', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={['proj-1', 'proj-2']} onChange={onChange} />)

      await user.click(screen.getByRole('button', { name: 'Clear all' }))

      expect(onChange).toHaveBeenCalledWith([])
    })
  })

  describe('filtering', () => {
    it('filters options by typed text', async () => {
      const user = userEvent.setup()
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={[]} onChange={vi.fn()} />)

      const input = screen.getByPlaceholderText('Select projects...')
      await user.click(input)
      await user.type(input, 'alpha')

      expect(screen.getByText('Alpha Project')).toBeInTheDocument()
      expect(screen.queryByText('Beta Project')).not.toBeInTheDocument()
      expect(screen.queryByText('Gamma Project')).not.toBeInTheDocument()
    })

    it('shows no results message for unmatched filter', async () => {
      const user = userEvent.setup()
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={[]} onChange={vi.fn()} />)

      const input = screen.getByPlaceholderText('Select projects...')
      await user.click(input)
      await user.type(input, 'nonexistent')

      expect(screen.getByText('No results match "nonexistent"')).toBeInTheDocument()
    })

    it('clears filter when dropdown is closed', async () => {
      const user = userEvent.setup()
      mockProjectsLoaded()
      render(<ProjectMultiSelect selectedIds={[]} onChange={vi.fn()} />)

      const input = screen.getByPlaceholderText('Select projects...')
      await user.click(input)
      await user.type(input, 'alpha')
      expect(screen.queryByText('Beta Project')).not.toBeInTheDocument()

      await user.keyboard('{Escape}')
      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
      })

      await user.click(input)
      expect(screen.getByText('Alpha Project')).toBeInTheDocument()
      expect(screen.getByText('Beta Project')).toBeInTheDocument()
    })
  })

  describe('loading state', () => {
    it('shows loading message when projects are loading', async () => {
      const user = userEvent.setup()
      mockProjectsLoading()
      render(<ProjectMultiSelect selectedIds={[]} onChange={vi.fn()} />)

      await user.click(screen.getByPlaceholderText('Select projects...'))

      expect(screen.getByText('Loading projects...')).toBeInTheDocument()
    })
  })

  describe('empty state', () => {
    it('shows "No projects available" when there are no projects', async () => {
      const user = userEvent.setup()
      mockProjectsLoaded([])
      render(<ProjectMultiSelect selectedIds={[]} onChange={vi.fn()} />)

      await user.click(screen.getByPlaceholderText('Select projects...'))

      expect(screen.getByText('No projects available')).toBeInTheDocument()
    })
  })

  describe('scroll behavior', () => {
    it('attaches scroll listeners to scrollable ancestors and closes on scroll', async () => {
      const user = userEvent.setup()
      mockProjectsLoaded()

      const scrollParent = document.createElement('div')
      Object.defineProperty(scrollParent, 'scrollHeight', { value: 500, configurable: true })
      Object.defineProperty(scrollParent, 'clientHeight', { value: 300, configurable: true })
      const addEventSpy = vi.spyOn(scrollParent, 'addEventListener')

      const renderTarget = document.createElement('div')
      scrollParent.appendChild(renderTarget)
      document.body.appendChild(scrollParent)

      render(<ProjectMultiSelect selectedIds={[]} onChange={vi.fn()} />, { container: renderTarget })

      await user.click(screen.getByPlaceholderText('Select projects...'))

      expect(addEventSpy).toHaveBeenCalledWith('scroll', expect.any(Function), { passive: true })

      document.body.removeChild(scrollParent)
    })
  })

  describe('accessibility', () => {
    it('has no accessibility violations with no selection', async () => {
      mockProjectsLoaded()
      const { container } = render(<ProjectMultiSelect selectedIds={[]} onChange={vi.fn()} />)

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })

    it('has no accessibility violations with selected projects', async () => {
      mockProjectsLoaded()
      const { container } = render(<ProjectMultiSelect selectedIds={['proj-1', 'proj-2']} onChange={vi.fn()} />)

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })
  })
})
