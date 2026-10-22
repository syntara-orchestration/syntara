// Concise guide content curated from backend/docs/workflow-management.md,
// backend/docs/workflow-engine/, backend/docs/approvals/approval-overview.md,
// and frontend/docs/workflow-loading-saving.md.

export const WORKFLOW_GUIDE_TOPICS = [
  'overview',
  'workflow_graph',
  'triggers',
  'step_types',
  'configuring_steps',
  'saving_and_running',
] as const

export const WORKFLOW_GUIDE_SCHEMA = {
  type: 'object',
  required: ['topic'],
  additionalProperties: false,
  properties: {
    topic: {
      type: 'string',
      enum: WORKFLOW_GUIDE_TOPICS,
      description:
        'Choose one concise section: overview (what Syntara does), workflow_graph (steps and branches), triggers, step_types, configuring_steps, or saving_and_running.',
    },
  },
}

type WorkflowGuideSection = {
  title: string
  summary: string
  key_points: string[]
}

const WORKFLOW_GUIDES: Record<string, WorkflowGuideSection> = {
  overview: {
    title: 'Syntara overview',
    summary:
      'Syntara is a distributed multi-agent automation system. Teams use workflows to coordinate AI agent tasks, human decisions, and external systems.',
    key_points: ['This page is the workflow builder: design, configure, validate, and save a workflow to a project.'],
  },
  workflow_graph: {
    title: 'Workflow basics',
    summary: 'A workflow is a directed graph of triggers, steps, and connections.',
    key_points: [
      'Triggers are entry points; nodes perform work or control flow; edges define what can run next.',
      'Conditions and switches route work. Approvals branch on approved or rejected. Loops repeat; converge waits for configured branches.',
      'Multiple outgoing edges from a regular step can run in parallel.',
    ],
  },
  triggers: {
    title: 'Workflow triggers',
    summary:
      'Triggers start an execution. Syntara supports manual, webhook, Event-Driven Ansible (EDA), and scheduled triggers.',
    key_points: [
      'A workflow can define multiple triggers, but each execution selects one.',
      'The WebMCP draft creator currently adds one manual trigger.',
    ],
  },
  step_types: {
    title: 'Workflow step types',
    summary:
      'The builder includes AI agent, approval, script, HTTP request, Ansible Automation Platform (AAP) job and workflow job, condition, switch, loop, wait, and converge steps.',
    key_points: [
      'WebMCP draft creation currently supports AI agent, approval, AAP job, AAP workflow job, and HTTP request steps, up to ten in sequence.',
      'Draft creation follows the approved path after an approval. Use the canvas to add a rejected route or other branching.',
    ],
  },
  configuring_steps: {
    title: 'Configuring workflow steps',
    summary: 'Step settings depend on the selected node type and the integrations configured for its project.',
    key_points: [
      'AI agent steps require a prompt; choose a model and tool access when needed. Approval steps can specify a prompt and approvers.',
      'AAP steps need a configured integration, credential reference, and job template ID or name. HTTP steps need a method and URL.',
      'Use credential references, never secret values, in tool inputs. Later steps can reference trigger or earlier-step outputs with expressions.',
    ],
  },
  saving_and_running: {
    title: 'Saving and running workflows',
    summary: 'A new workflow needs a selected project before it can be saved.',
    key_points: [
      'Validate the graph and node configuration, then save. Saving does not start an execution.',
      'A run request checks readiness and opens Syntara’s confirmation dialog. A person confirms and provides trigger inputs when needed.',
    ],
  },
}

export function getWorkflowGuide(topic: unknown): WorkflowGuideSection | null {
  if (typeof topic !== 'string') return null
  return WORKFLOW_GUIDES[topic] ?? null
}
