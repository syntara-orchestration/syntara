/**
 * Auto-generated from backend JSON Schema files.
 * DO NOT EDIT — run `npm run gen` to regenerate.
 *
 * Source: backend/src/syntara/schemas/workflows/v2/
 */

export interface OutputFieldDef {
  name: string
  type: 'string' | 'number' | 'boolean' | 'object' | 'array' | 'unknown'
  description: string
}

export const NODE_OUTPUT_SCHEMAS: Record<string, OutputFieldDef[]> = {
  scheduled_trigger: [
    {
      name: 'scheduled_at',
      type: 'string',
      description: 'ISO 8601 timestamp of when the execution was scheduled to fire',
    },
    { name: 'triggered_at', type: 'string', description: 'ISO 8601 timestamp of when the execution actually started' },
  ],
  script: [
    { name: 'status', type: 'string', description: 'Script execution completed' },
    { name: 'return_code', type: 'number', description: 'Script exit code (0 = success)' },
    { name: 'stdout', type: 'string', description: 'Standard output from script execution' },
    { name: 'stderr', type: 'string', description: 'Standard error from script execution' },
    {
      name: 'stdout_json',
      type: 'unknown',
      description:
        'Parsed JSON from stdout (Python scripts only). Present if stdout contains valid JSON (entire stdout or last line).',
    },
  ],
  aap_job_template: [
    { name: 'status', type: 'string', description: 'Execution succeeded' },
    { name: 'job_id', type: 'number', description: 'Ansible Automation Platform job ID' },
    { name: 'job_status', type: 'string', description: 'Job status (successful, failed, etc.)' },
    { name: 'created', type: 'string', description: 'Job creation timestamp (ISO 8601)' },
    { name: 'started', type: 'string', description: 'Job start timestamp (ISO 8601)' },
    { name: 'finished', type: 'string', description: 'Job finish timestamp (ISO 8601)' },
    { name: 'job_url', type: 'string', description: 'URL to view job in Ansible Automation Platform UI' },
    { name: 'artifacts', type: 'object', description: 'Job artifacts/facts' },
  ],
  aap_workflow_job_template: [
    { name: 'status', type: 'string', description: 'Execution succeeded' },
    { name: 'workflow_job_id', type: 'number', description: 'Ansible Automation Platform workflow job ID' },
    { name: 'created', type: 'string', description: 'Workflow job creation timestamp (ISO 8601)' },
    { name: 'started', type: 'string', description: 'Workflow job start timestamp (ISO 8601)' },
    { name: 'finished', type: 'string', description: 'Workflow job finish timestamp (ISO 8601)' },
    {
      name: 'workflow_job_url',
      type: 'string',
      description: 'URL to view workflow job in Ansible Automation Platform UI',
    },
    { name: 'workflow_job_status', type: 'string', description: 'Workflow job status (successful, failed, etc.)' },
    { name: 'artifacts', type: 'object', description: 'Workflow job artifacts' },
  ],
  http_request: [
    { name: 'status', type: 'string', description: 'Execution succeeded' },
    { name: 'status_code', type: 'number', description: 'HTTP status code' },
    { name: 'body', type: 'unknown', description: 'Response body (parsed JSON or raw string)' },
    { name: 'headers', type: 'object', description: 'Response headers' },
    { name: 'elapsed', type: 'number', description: 'Request duration in seconds' },
  ],
  agentic: [
    { name: 'status', type: 'string', description: 'Execution succeeded' },
    {
      name: 'output',
      type: 'unknown',
      description:
        'Agent response output - either string (unstructured) or object (structured based on response_schema)',
    },
    { name: 'tool_calls', type: 'array', description: 'List of tool calls made by the agent during execution' },
    { name: 'used_tools', type: 'array', description: 'Aggregated tool usage with tool names and call counts' },
    {
      name: 'structured_output_metadata',
      type: 'object',
      description: 'Metadata about structured output generation when response_schema is defined',
    },
    {
      name: 'integration_ids',
      type: 'unknown',
      description: 'UUIDs of integrations used during execution (captured at runtime from integration_connections)',
    },
  ],
  approval: [
    { name: 'status', type: 'string', description: 'Approval decision was made' },
    {
      name: 'decided_by',
      type: 'string',
      description: "Username of the user who made the decision (or 'system' for timeout/cancellation)",
    },
    { name: 'decision', type: 'string', description: 'Detailed decision outcome' },
    { name: 'decided_at', type: 'string', description: 'When the decision occurred (ISO 8601)' },
    {
      name: 'decision_notes',
      type: 'string',
      description: "Optional notes provided by approver or system (e.g., 'Auto-rejected due to timeout')",
    },
  ],
  internal_activity: [{ name: 'status', type: 'string', description: 'Operation result status' }],
  condition: [
    { name: 'status', type: 'string', description: 'Condition evaluated successfully' },
    { name: 'evaluated_result', type: 'boolean', description: 'Result of condition evaluation (true or false)' },
  ],
  loop: [
    { name: 'status', type: 'string', description: 'Loop completed successfully' },
    { name: 'iteration_count', type: 'number', description: 'Number of iterations completed' },
    {
      name: 'iteration_results',
      type: 'object',
      description:
        'Aggregated variables from loop body iterations. Key = variable name with namespace (node_id.output_field), Value = list of values from each iteration.',
    },
  ],
  converge: [
    { name: 'status', type: 'string', description: 'Convergence completed successfully' },
    { name: 'branch_count', type: 'number', description: 'Total number of incoming parallel branches' },
    {
      name: 'completed_count',
      type: 'number',
      description:
        "Number of branches that completed before convergence triggered. Equals branch_count for 'all' strategy.",
    },
    {
      name: 'completed_branch_node_ids',
      type: 'array',
      description:
        'Node IDs of completed branches. Users can reference these nodes directly for outputs (e.g., ${task_a.result}).',
    },
  ],
  switch: [
    { name: 'status', type: 'string', description: 'Switch evaluated successfully' },
    { name: 'matched_port', type: 'string', description: 'Port that was selected for routing' },
  ],
  wait: [{ name: 'status', type: 'string', description: 'Wait duration elapsed successfully' }],
  tfe_create_workspace: [
    { name: 'workspace_id', type: 'unknown', description: '' },
    { name: 'workspace_name', type: 'unknown', description: '' },
    { name: 'organization', type: 'unknown', description: '' },
  ],
  tfe_list_workspaces: [
    { name: 'workspaces', type: 'unknown', description: '' },
    { name: 'count', type: 'unknown', description: '' },
  ],
  tfe_update_workspace: [{ name: 'workspace_id', type: 'unknown', description: '' }],
  tfe_delete_workspace: [{ name: 'deleted', type: 'unknown', description: '' }],
  tfe_fetch_state_outputs: [
    { name: 'has_state', type: 'unknown', description: '' },
    { name: 'state_version_id', type: 'unknown', description: '' },
    { name: 'outputs', type: 'unknown', description: '' },
  ],
  tfe_add_variable: [{ name: 'variable_id', type: 'unknown', description: '' }],
  tfe_list_variables: [
    { name: 'variables', type: 'unknown', description: '' },
    { name: 'count', type: 'unknown', description: '' },
  ],
  tfe_update_variable: [{ name: 'variable_id', type: 'unknown', description: '' }],
  tfe_delete_variable: [{ name: 'deleted', type: 'unknown', description: '' }],
  tfe_upload_configuration_version: [{ name: 'configuration_version_id', type: 'unknown', description: '' }],
  tfe_trigger_run: [
    { name: 'run_id', type: 'unknown', description: '' },
    { name: 'mode', type: 'unknown', description: '' },
    { name: 'status', type: 'unknown', description: '' },
  ],
  tfe_get_run_status: [
    { name: 'run_id', type: 'unknown', description: '' },
    { name: 'status', type: 'unknown', description: '' },
    { name: 'phase', type: 'unknown', description: '' },
    { name: 'plan_exit_code', type: 'unknown', description: '' },
    { name: 'has_changes', type: 'unknown', description: '' },
    { name: 'resource_changes', type: 'unknown', description: '' },
    { name: 'is_confirmable', type: 'unknown', description: '' },
    { name: 'is_cancelable', type: 'unknown', description: '' },
    { name: 'is_force_cancelable', type: 'unknown', description: '' },
  ],
  tfe_apply_run: [
    { name: 'run_id', type: 'unknown', description: '' },
    { name: 'action_queued', type: 'unknown', description: '' },
  ],
  tfe_discard_run: [
    { name: 'run_id', type: 'unknown', description: '' },
    { name: 'action_queued', type: 'unknown', description: '' },
  ],
  tfe_cancel_run: [
    { name: 'run_id', type: 'unknown', description: '' },
    { name: 'action_queued', type: 'unknown', description: '' },
  ],
  tfe_force_cancel_run: [
    { name: 'run_id', type: 'unknown', description: '' },
    { name: 'action_queued', type: 'unknown', description: '' },
  ],
  tfe_list_runs: [
    { name: 'runs', type: 'unknown', description: '' },
    { name: 'count', type: 'unknown', description: '' },
  ],
  tfe_add_run_comment: [{ name: 'comment_id', type: 'unknown', description: '' }],
  tfe_list_github_installations: [
    { name: 'installations', type: 'unknown', description: '' },
    { name: 'count', type: 'unknown', description: '' },
  ],
  tfe_get_github_installation: [
    { name: 'installation_id', type: 'unknown', description: '' },
    { name: 'owner', type: 'unknown', description: '' },
    { name: 'display_name', type: 'unknown', description: '' },
    { name: 'repositories', type: 'unknown', description: '' },
  ],
  tfe_link_vcs: [
    { name: 'linked', type: 'unknown', description: '' },
    { name: 'identifier', type: 'unknown', description: '' },
    { name: 'branch', type: 'unknown', description: '' },
  ],
  tfe_create_project: [{ name: 'project_id', type: 'unknown', description: '' }],
  tfe_list_projects: [
    { name: 'projects', type: 'unknown', description: '' },
    { name: 'count', type: 'unknown', description: '' },
  ],
  tfe_get_project: [
    { name: 'project_id', type: 'unknown', description: '' },
    { name: 'name', type: 'unknown', description: '' },
    { name: 'description', type: 'unknown', description: '' },
    { name: 'teams', type: 'unknown', description: '' },
  ],
  tfe_update_project: [{ name: 'project_id', type: 'unknown', description: '' }],
  tfe_delete_project: [{ name: 'deleted', type: 'unknown', description: '' }],
  tfe_move_workspace_to_project: [
    { name: 'workspace_id', type: 'unknown', description: '' },
    { name: 'project_id', type: 'unknown', description: '' },
  ],
  tfe_assign_team_permissions: [
    { name: 'project_id', type: 'unknown', description: '' },
    { name: 'team_id', type: 'unknown', description: '' },
    { name: 'access', type: 'unknown', description: '' },
  ],
}

export function getNodeOutputSchema(nodeType: string): OutputFieldDef[] | null {
  return NODE_OUTPUT_SCHEMAS[nodeType] ?? null
}
