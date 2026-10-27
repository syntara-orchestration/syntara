import type { TaskActivity } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual('@xyflow/react')
  return {
    ...actual,
    useStore: (selector: (s: { nodesConnectable: boolean }) => boolean) => selector({ nodesConnectable: true }),
  }
})

vi.mock('./renderStepIcon', () => ({
  renderStepIcon: () => null,
}))

vi.mock('./hooks/useCredentialName', () => ({
  useCredentialName: () => ({ name: undefined, isPending: false }),
}))

import { TaskActivityDetails } from './TaskNode'

describe('TaskActivityDetails', () => {
  it('renders script task details correctly', () => {
    const mockScriptTask = {
      type: 'script',
      id: 'task-1',
      name: 'Script Task',
      parameters: {
        language: 'python',
        code: 'print("hello")',
      },
    } as TaskActivity

    render(<TaskActivityDetails data={mockScriptTask} />)

    expect(screen.getByText('Script Task')).toBeInTheDocument()
    expect(screen.getByText('Script')).toBeInTheDocument()
    expect(screen.getByText('Language')).toBeInTheDocument()
    expect(screen.getByText('python')).toBeInTheDocument()
  })

  it('renders http_request task details correctly', () => {
    const mockHttpTask = {
      type: 'http_request',
      id: 'task-2',
      name: 'HTTP Request Task',
      parameters: {
        method: 'GET',
        url: 'https://api.example.com',
      },
    } as TaskActivity

    render(<TaskActivityDetails data={mockHttpTask} />)

    expect(screen.getByText('HTTP Request Task')).toBeInTheDocument()
    expect(screen.getByText('REST API')).toBeInTheDocument()
    expect(screen.getByText('GET')).toBeInTheDocument()
    expect(screen.getByText('https://api.example.com')).toBeInTheDocument()
  })

  it('renders agentic task details correctly', () => {
    const mockAgenticTask = {
      type: 'agentic',
      id: 'task-4',
      name: 'Incident Triage Agent',
      parameters: {
        model: 'claude-3-sonnet',
        prompt: 'Analyze the data and provide insights',
        tool_selection_strategy: 'SELECTED',
        tool_selections: ['calculator', 'web_search'],
      },
    } as TaskActivity

    render(<TaskActivityDetails data={mockAgenticTask} />)

    expect(screen.getByText('Incident Triage Agent')).toBeInTheDocument()
    expect(screen.getByText('Task Agent')).toBeInTheDocument()
    expect(screen.getByText('Model')).toBeInTheDocument()
    expect(screen.getByText('claude-3-sonnet')).toBeInTheDocument()
    expect(screen.getByText('Tools')).toBeInTheDocument()
    expect(screen.getByText('2 tools')).toBeInTheDocument()
  })

  it('renders AAP job template with static name', () => {
    const mockAAPTask = {
      type: 'aap_job_template',
      id: 'task-5',
      name: 'Launch Job',
      parameters: {
        job_template_name: 'Demo template',
        job_template_id: 123,
      },
    } as TaskActivity

    render(<TaskActivityDetails data={mockAAPTask} />)

    expect(screen.getByText('Launch Job')).toBeInTheDocument()
    expect(screen.getByText('Job template')).toBeInTheDocument()
    expect(screen.getByText('Demo template')).toBeInTheDocument()
  })

  it('renders AAP job template expression with expression label and shows the expression', () => {
    const mockAAPTask = {
      type: 'aap_job_template',
      id: 'task-6',
      name: 'Dynamic Launch Job',
      parameters: {
        job_template_name: '${name_via_ai.analysis.default_job_template}',
        job_template_id: 123,
      },
    } as TaskActivity

    render(<TaskActivityDetails data={mockAAPTask} />)

    expect(screen.getByText('Dynamic Launch Job')).toBeInTheDocument()
    expect(screen.getByText('Job template expression')).toBeInTheDocument()
    expect(screen.getByText('${name_via_ai.analysis.default_job_template}')).toBeInTheDocument()
  })

  it('renders AAP workflow template name when provided', () => {
    const mockAAPWFTask = {
      type: 'aap_workflow_job_template',
      id: 'task-7',
      name: 'Launch Workflow',
      parameters: {
        workflow_job_template_name: 'my-long-workflow-template-name',
      },
    } as TaskActivity

    render(<TaskActivityDetails data={mockAAPWFTask} />)

    expect(screen.getByText('Launch Workflow')).toBeInTheDocument()
    expect(screen.getByText('Workflow job template')).toBeInTheDocument()
    expect(screen.getByText('my-long-workflow-template-name')).toBeInTheDocument()
  })

  it('renders AAP workflow template expression with expression label and shows the expression', () => {
    const mockAAPWFTask = {
      type: 'aap_workflow_job_template',
      id: 'task-8',
      name: 'Dynamic Launch Workflow',
      parameters: {
        workflow_job_template_name: '{{workflow.context.template_name}}',
      },
    } as TaskActivity

    render(<TaskActivityDetails data={mockAAPWFTask} />)

    expect(screen.getByText('Dynamic Launch Workflow')).toBeInTheDocument()
    expect(screen.getByText('Workflow job template expression')).toBeInTheDocument()
    expect(screen.getByText('{{workflow.context.template_name}}')).toBeInTheDocument()
  })

  it('renders agentic task with model', () => {
    const mockAgenticTaskWithModel = {
      type: 'agentic',
      id: 'task-9',
      name: 'Task Agent with Model',
      parameters: {
        model: 'claude-3-opus',
        prompt: 'Analyze these files',
        tool_selection_strategy: 'SELECTED',
        tool_selections: ['code_analysis'],
      },
    } as TaskActivity

    render(<TaskActivityDetails data={mockAgenticTaskWithModel} />)

    expect(screen.getByText('Task Agent with Model')).toBeInTheDocument()
    expect(screen.getByText('claude-3-opus')).toBeInTheDocument()
  })
})
