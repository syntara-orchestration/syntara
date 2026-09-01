import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ScopeFields } from './ScopeFields'

vi.mock('../../../access/useAllProjects', () => {
  const projectsMock = vi.fn(() => ({
    projects: [
      { id: 'p-001', name: 'default' },
      { id: 'p-002', name: 'alice-sandbox' },
    ],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }))
  return { useAllProjects: projectsMock, useSelectableProjects: projectsMock }
})

type TestFormValues = {
  scope: string
  project_ids: string[]
}

function TestWrapper({
  defaultScope = 'global',
  defaultProjectIds = [] as string[],
  onScopeChange,
}: {
  defaultScope?: string
  defaultProjectIds?: string[]
  onScopeChange?: (newScope: string) => void
}) {
  const { control } = useForm<TestFormValues>({
    defaultValues: {
      scope: defaultScope,
      project_ids: defaultProjectIds,
    },
  })

  const scope = useWatch({ control, name: 'scope' })

  return (
    <ScopeFields<TestFormValues>
      control={control}
      scope={scope}
      scopeName="scope"
      projectIdsName="project_ids"
      idPrefix="test"
      onScopeChange={onScopeChange}
    />
  )
}

describe('ScopeFields', () => {
  describe('scope toggle rendering', () => {
    it('renders scope toggle in global state (checked)', () => {
      render(<TestWrapper defaultScope="global" />)

      const toggle = screen.getByRole('switch', { name: /integration scope/i })
      expect(toggle).toBeChecked()
    })

    it('renders scope toggle in project state (unchecked)', () => {
      render(<TestWrapper defaultScope="project" />)

      const toggle = screen.getByRole('switch', { name: /integration scope/i })
      expect(toggle).not.toBeChecked()
    })
  })

  describe('ProjectMultiSelect visibility', () => {
    it('shows ProjectMultiSelect when scope is project', () => {
      render(<TestWrapper defaultScope="project" />)

      expect(screen.getByText('Projects')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Select projects...')).toBeInTheDocument()
    })

    it('hides ProjectMultiSelect when scope is global', () => {
      render(<TestWrapper defaultScope="global" />)

      expect(screen.queryByText('Projects')).not.toBeInTheDocument()
      expect(screen.queryByPlaceholderText('Select projects...')).not.toBeInTheDocument()
    })
  })

  describe('helper text', () => {
    it('shows global helper text when scope is global', () => {
      render(<TestWrapper defaultScope="global" />)

      expect(
        screen.getByText(
          'Global integrations are available to all projects. Turn off to scope this integration to specific projects.'
        )
      ).toBeInTheDocument()
    })

    it('shows project helper text when scope is project', () => {
      render(<TestWrapper defaultScope="project" />)

      expect(screen.getByText('This integration will only be available to selected projects.')).toBeInTheDocument()
    })
  })

  describe('toggle interaction', () => {
    it('calls onScopeChange when toggle is clicked from global to project', async () => {
      const onScopeChange = vi.fn()
      const user = userEvent.setup()
      render(<TestWrapper defaultScope="global" onScopeChange={onScopeChange} />)

      await user.click(screen.getByRole('switch', { name: /integration scope/i }))

      expect(onScopeChange).toHaveBeenCalledWith('project')
    })

    it('calls onScopeChange when toggle is clicked from project to global', async () => {
      const onScopeChange = vi.fn()
      const user = userEvent.setup()
      render(<TestWrapper defaultScope="project" onScopeChange={onScopeChange} />)

      await user.click(screen.getByRole('switch', { name: /integration scope/i }))

      expect(onScopeChange).toHaveBeenCalledWith('global')
    })

    it('shows ProjectMultiSelect after toggling from global to project', async () => {
      const user = userEvent.setup()
      render(<TestWrapper defaultScope="global" />)

      expect(screen.queryByPlaceholderText('Select projects...')).not.toBeInTheDocument()

      await user.click(screen.getByRole('switch', { name: /integration scope/i }))

      expect(screen.getByPlaceholderText('Select projects...')).toBeInTheDocument()
    })

    it('hides ProjectMultiSelect after toggling from project to global', async () => {
      const user = userEvent.setup()
      render(<TestWrapper defaultScope="project" />)

      expect(screen.getByPlaceholderText('Select projects...')).toBeInTheDocument()

      await user.click(screen.getByRole('switch', { name: /integration scope/i }))

      expect(screen.queryByPlaceholderText('Select projects...')).not.toBeInTheDocument()
    })
  })

  describe('project selection', () => {
    it('updates selected project ids when a project is chosen', async () => {
      const user = userEvent.setup()

      function ProjectSelectionProbe() {
        const { control } = useForm<TestFormValues>({
          defaultValues: { scope: 'project', project_ids: [] },
        })
        const projectIds = useWatch({ control, name: 'project_ids' })

        return (
          <>
            <ScopeFields<TestFormValues>
              control={control}
              scope="project"
              scopeName="scope"
              projectIdsName="project_ids"
              idPrefix="test"
            />
            <output data-testid="selected-projects">{projectIds.join(',')}</output>
          </>
        )
      }

      render(<ProjectSelectionProbe />)

      await user.click(screen.getByPlaceholderText('Select projects...'))
      await user.click(screen.getByText('alice-sandbox'))

      expect(screen.getByTestId('selected-projects')).toHaveTextContent('p-002')
    })

    it('shows project field validation errors from the form controller', () => {
      function ErrorProbe() {
        const { control, setError } = useForm<TestFormValues>({
          defaultValues: { scope: 'project', project_ids: [] },
        })

        useEffect(() => {
          setError('project_ids', { type: 'required', message: 'Select at least one project' })
        }, [setError])

        return (
          <ScopeFields<TestFormValues>
            control={control}
            scope="project"
            scopeName="scope"
            projectIdsName="project_ids"
            idPrefix="test"
          />
        )
      }

      render(<ErrorProbe />)

      expect(screen.getByText('Select at least one project')).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has no accessibility violations with global scope', async () => {
      const { container } = render(<TestWrapper defaultScope="global" />)

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })

    it('has no accessibility violations with project scope', async () => {
      const { container } = render(<TestWrapper defaultScope="project" />)

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })
  })
})
