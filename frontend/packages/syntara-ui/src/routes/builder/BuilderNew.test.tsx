import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { expectPageTitle } from '../../test/pageTitle'

import BuilderNew from './BuilderNew'

const prefetchQuery = vi.fn()
vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return { ...actual, useQueryClient: () => ({ prefetchQuery }) }
})

vi.mock('../../client', () => ({
  workflowClient: {
    queryOptions: vi.fn().mockReturnValue({ queryKey: [], queryFn: vi.fn() }),
  },
}))

const navigate = vi.fn()
const searchState: { projectId?: string } = {}
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => navigate,
    useSearch: ({ select }: { select: (search: unknown) => unknown }) => select({ ...searchState }),
  }
})

type SelectorState = {
  selectedProject: { id: string; name: string; is_builtin?: boolean } | null
  selectedProjectId: string | null
}
const selectorState: SelectorState = { selectedProject: null, selectedProjectId: null }
const useProjectSelectorMock = vi.fn<(options: Record<string, unknown>) => unknown>(() => ({
  ...selectorState,
  ProjectSelector: <input aria-label="Project" placeholder="Select a project" />,
}))
vi.mock('../../hooks/useProjectSelector', () => ({
  useProjectSelector: (options: Record<string, unknown>) => useProjectSelectorMock(options),
}))

const onlyProject: { id: string | undefined } = { id: undefined }
vi.mock('./hooks/useOnlyWorkflowProjectId', () => ({
  useOnlyWorkflowProjectId: () => onlyProject.id,
}))

const builderContentProps = vi.fn()
vi.mock('./BuilderContent', () => ({
  BuilderContent: (props: Record<string, unknown>) => {
    builderContentProps(props)
    return <div data-testid="builder-content" />
  },
}))

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return { ...actual, ReactFlowProvider: ({ children }: { children: React.ReactNode }) => <>{children}</> }
})

function selectProject(project: SelectorState['selectedProject']) {
  selectorState.selectedProject = project
  selectorState.selectedProjectId = project?.id ?? null
}

function lastSelectorOptions() {
  return useProjectSelectorMock.mock.calls.at(-1)?.[0]
}

describe('BuilderNew', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    delete searchState.projectId
    onlyProject.id = undefined
    selectProject(null)
  })

  it('sets the browser tab title', () => {
    render(<BuilderNew />)
    expectPageTitle('New Workflow | Workflows | Syntara')
  })

  it('asks for a project before opening the builder', () => {
    render(<BuilderNew />)
    expect(screen.getByRole('dialog', { name: 'Select a project' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Project' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    expect(screen.queryByTestId('builder-content')).not.toBeInTheDocument()
  })

  it('never inherits the project selected on another page', () => {
    render(<BuilderNew />)
    expect(lastSelectorOptions()).toMatchObject({
      requireProject: true,
      clearSelectionOnMount: true,
      initialProjectId: undefined,
      showTogglePrefix: false,
      isMenuInline: true,
    })
  })

  it('pre-fills the project from ?projectId', () => {
    searchState.projectId = 'proj-1'
    onlyProject.id = 'proj-only'
    render(<BuilderNew />)
    expect(lastSelectorOptions()).toMatchObject({ initialProjectId: 'proj-1' })
  })

  it('pre-fills the only project when there is no ?projectId', () => {
    onlyProject.id = 'proj-only'
    render(<BuilderNew />)
    expect(lastSelectorOptions()).toMatchObject({ initialProjectId: 'proj-only' })
  })

  it('still asks to confirm a pre-filled project', () => {
    searchState.projectId = 'proj-1'
    selectProject({ id: 'proj-1', name: 'payments' })
    render(<BuilderNew />)
    expect(screen.getByRole('dialog', { name: 'Select a project' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
    expect(screen.queryByTestId('builder-content')).not.toBeInTheDocument()
  })

  it('blocks built-in projects', () => {
    selectProject({ id: 'builtin', name: 'Built-in', is_builtin: true })
    render(<BuilderNew />)
    expect(screen.getByText(/Built-in projects cannot contain new workflows/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
  })

  it('opens the builder with the confirmed project after Continue', async () => {
    const user = userEvent.setup()
    selectProject({ id: 'proj-1', name: 'payments' })
    const { rerender } = render(<BuilderNew />)

    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(navigate).toHaveBeenCalledWith({ to: '/workflow-builder/new', search: { projectId: 'proj-1' } })
    expect(prefetchQuery).toHaveBeenCalled()

    searchState.projectId = 'proj-1'
    rerender(<BuilderNew />)
    expect(screen.queryByRole('dialog', { name: 'Select a project' })).not.toBeInTheDocument()
    expect(screen.getByTestId('builder-content')).toBeInTheDocument()
    expect(builderContentProps).toHaveBeenLastCalledWith(
      expect.objectContaining({ isNew: true, workflowId: null, initialProjectId: 'proj-1' })
    )
  })

  it('goes back to the workflows list on Cancel', async () => {
    const user = userEvent.setup()
    render(<BuilderNew />)
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(navigate).toHaveBeenCalledWith({ to: '/workflows' })
  })

  it('has no accessibility violations', async () => {
    selectProject({ id: 'proj-1', name: 'payments' })
    render(<BuilderNew />)
    expect(await axe(document.body)).toHaveNoViolations()
  })
})
