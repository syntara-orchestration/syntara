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
      'A workflow can define multiple triggers, but each execution selects one. The draft tool supports manual, scheduled, webhook, and EDA triggers.',
      'Trigger parameters use backend keys: input_schema for manual/webhook/EDA; schedule_type with cron or interval for scheduled; webhook_path and authorized_service_account_ids for webhook/EDA.',
    ],
  },
  step_types: {
    title: 'Workflow step types',
    summary:
      'The builder includes AI agent, approval, script, HTTP request, Ansible Automation Platform (AAP) job and workflow job, condition, switch, loop, wait, and converge steps.',
    key_points: [
      'WebMCP draft creation supports every user-selectable builder node type: agentic, script, http_request, aap_job_template, aap_workflow_job_template, approval, condition, switch, loop, wait, and converge.',
      'Use nodes plus edges to build branches, parallel paths, and loop bodies. The steps shortcut remains for simple ordered chains of agentic, approval, AAP, and HTTP request nodes.',
      'Generic placeholders and internal_activity are not user-selectable workflow steps; the builder uses them for incomplete loop bodies or system workflows.',
    ],
  },
  configuring_steps: {
    title: 'Configuring workflow steps',
    summary: 'Step settings depend on the selected node type and the integrations configured for its project.',
    key_points: [
      'Pass node parameters in backend format: scripts use language/code; HTTP uses method/url/headers/body; agents use prompt/model/tool selections; approval uses prompt/approvers; AAP uses template and integration references.',
      'Condition uses a condition expression; switch uses cases with case_0 ports and a default port; loop uses type for_each with items or do_while with condition; wait uses duration; converge uses strategy all/any. Put timeout and retry_policy in node settings.',
      'Edges use node IDs or trigger-0, trigger-1 references. Branch handles are true/false, case_0/default, approved/rejected, and loop/done. Use target_handle end for a loop-back edge.',
      'Use credential references, never secret values, in tool inputs. Later steps can reference trigger or earlier-step outputs with expressions.',
    ],
  },
  saving_and_running: {
    title: 'Saving and running workflows',
    summary: 'Start from the Workflows page, choose a project, then validate and save the new workflow.',
    key_points: [
      'From the Workflows page, open a blank builder with open_new_workflow_builder. In the builder, select a non-built-in project by exact name or ID with select_workflow_project.',
      'Validate the graph and node configuration, then save. Saving does not start an execution.',
      'A run request checks readiness and opens Syntara’s confirmation dialog. A person confirms and provides trigger inputs when needed.',
    ],
  },
}

export function getWorkflowGuide(topic: unknown): WorkflowGuideSection | null {
  if (typeof topic !== 'string') return null
  return WORKFLOW_GUIDES[topic] ?? null
}
