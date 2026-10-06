import type { FormsAPI } from '@syntara/contracts'

import { mockDate } from './mockDates'

type FormPromptRead = FormsAPI.components['schemas']['FormPromptRead']
type FormPromptListRead = FormsAPI.components['schemas']['FormPromptListRead']

const MOCK_WORKFLOW_CONTEXT = {
  workflow_id: 'wf-form-prompt-demo',
  workflow_version: 1,
  workflow_name: 'Form prompt demo workflow',
} as const

const MINUTE_MS = 60 * 1000
const HOUR_MS = 60 * MINUTE_MS

/** Keeps pending prompt deadlines aligned with the browser clock in mock mode. */
export function alignPendingFormPromptClock(prompt: FormPromptRead): FormPromptRead {
  if (prompt.status !== 'pending') {
    return prompt
  }
  const now = Date.now()
  return {
    ...prompt,
    created_at: new Date(now - 10 * MINUTE_MS).toISOString(),
    updated_at: new Date(now - 10 * MINUTE_MS).toISOString(),
    timeout_at: new Date(now + 23 * HOUR_MS).toISOString(),
  }
}

const sampleFormDefinition: FormsAPI.components['schemas']['FormDefinition'] = {
  fields: [
    {
      value_name: 'reason',
      type: 'text',
      label: 'Reason',
      required: true,
      placeholder: 'Describe why you are approving this change',
    },
  ],
}

/** Maps a full form prompt record to the list-row shape returned by GET /form_prompts. */
export function formPromptToListRead(prompt: FormPromptRead): FormPromptListRead {
  return {
    id: prompt.id,
    created_at: prompt.created_at,
    execution_id: prompt.execution_id,
    project_id: prompt.project_id,
    prompt_node_id: prompt.prompt_node_id,
    name: prompt.name,
    status: prompt.status,
    timeout_at: prompt.timeout_at ?? null,
    responded_at: prompt.responded_at ?? null,
    responded_by: prompt.responded_by ?? null,
    workflow_id: MOCK_WORKFLOW_CONTEXT.workflow_id,
    workflow_version: MOCK_WORKFLOW_CONTEXT.workflow_version,
    workflow_name:
      prompt.id === 'fp-exec-form-prompt-2' ? 'Beta rollout workflow' : MOCK_WORKFLOW_CONTEXT.workflow_name,
  }
}

export const formPrompts: FormPromptRead[] = [
  {
    id: 'fp-exec-form-prompt-1',
    created_at: mockDate.minutesAgo10,
    updated_at: mockDate.minutesAgo10,
    labels: {},
    project_id: 'p-001',
    execution_id: 'exec-form-prompt',
    prompt_node_id: 'collect_input',
    name: 'Collect operator input',
    message: 'Provide details required to continue the workflow.',
    status: 'pending',
    timeout_at: mockDate.hoursFromNow23,
    form_definition: sampleFormDefinition,
    submit_label: 'Submit response',
    success_message: 'Thank you — the workflow will continue.',
    responder_users: [{ id: 'user-admin', username: 'admin' }],
    responder_groups: [],
    response_data: null,
    responded_at: null,
    responded_by: null,
  },
  {
    id: 'fp-exec-form-prompt-2',
    created_at: mockDate.daysAgo2,
    updated_at: mockDate.daysAgo1,
    labels: {},
    project_id: 'p-001',
    execution_id: 'exec-form-prompt',
    prompt_node_id: 'confirm_details',
    name: 'Confirm deployment details',
    message: 'Review the submitted values before the workflow continues.',
    status: 'submitted',
    timeout_at: mockDate.daysAgo1,
    form_definition: sampleFormDefinition,
    submit_label: 'Submit response',
    success_message: 'Thank you — the workflow will continue.',
    responder_users: [],
    responder_groups: [],
    response_data: { reason: 'Approved for production rollout' },
    responded_at: mockDate.daysAgo1,
    responded_by: { id: 'user-admin', name: 'Admin User', type: 'user' },
  },
]
