import { WEBMCP_WORKFLOW_NODE_TYPES, WEBMCP_WORKFLOW_STEP_TYPES, WEBMCP_WORKFLOW_TRIGGER_TYPES } from './workflowWebMcp'

const NODE_SETTINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    disabled: { type: 'boolean' },
    continue_on_failure: { type: 'boolean' },
    timeout: { type: 'number', minimum: 0, description: 'Timeout in seconds.' },
    retry_policy: {
      type: 'object',
      additionalProperties: false,
      properties: {
        max_retries: { type: 'integer', minimum: 0 },
        backoff: { type: 'string', enum: ['exponential', 'fixed'] },
        initial_interval: { type: 'number', minimum: 0 },
        max_interval: { type: 'number', minimum: 0 },
        backoff_coefficient: { type: 'number', minimum: 0 },
      },
    },
  },
}

export const DRAFT_SCHEMA = {
  type: 'object',
  description: 'Provide either steps for a simple chain or nodes plus edges for a graph. Do not provide both formats.',
  required: ['name', 'description'],
  additionalProperties: false,
  properties: {
    name: { type: 'string', maxLength: 255, description: 'Workflow name.' },
    description: { type: 'string', maxLength: 1024, description: 'What the workflow does.' },
    triggers: {
      type: 'array',
      minItems: 1,
      maxItems: 10,
      description:
        'Optional trigger definitions. If omitted, add one manual trigger. Types: manual_trigger, scheduled_trigger, webhook_trigger, eda_trigger. Parameters use backend keys such as input_schema, schedule_type/cron/interval, webhook_path, and authorized_service_account_ids.',
      items: {
        type: 'object',
        required: ['type'],
        additionalProperties: false,
        properties: {
          type: { type: 'string', enum: WEBMCP_WORKFLOW_TRIGGER_TYPES },
          name: { type: 'string', maxLength: 255 },
          parameters: {
            type: 'object',
            additionalProperties: true,
            description: 'Trigger parameters in Syntara backend format. Never include secret values.',
          },
        },
      },
    },
    steps: {
      type: 'array',
      minItems: 1,
      maxItems: 10,
      description:
        'Compatibility shortcut for a simple ordered chain. Supports agentic, approval, AAP job/workflow job, and HTTP request nodes. Use nodes and edges for any other node type or custom graph connections.',
      items: {
        type: 'object',
        required: ['type', 'name'],
        additionalProperties: false,
        properties: {
          type: { type: 'string', enum: WEBMCP_WORKFLOW_STEP_TYPES },
          name: { type: 'string', maxLength: 255 },
          parameters: {
            type: 'object',
            additionalProperties: true,
            description: 'Node parameters in Syntara backend format. Use credential references, never secret values.',
          },
          settings: { ...NODE_SETTINGS_SCHEMA, description: 'Optional engine settings for this node.' },
        },
      },
    },
    nodes: {
      type: 'array',
      minItems: 1,
      maxItems: 50,
      description:
        'Graph mode: define nodes with unique IDs, then connect them with edges. Supported types: script, http_request, agentic, aap_job_template, aap_workflow_job_template, approval, condition, loop, converge, switch, wait. Use backend parameter keys; see get_syntara_guide for node configuration and branch handles.',
      items: {
        type: 'object',
        required: ['id', 'type', 'name'],
        additionalProperties: false,
        properties: {
          id: {
            type: 'string',
            minLength: 1,
            maxLength: 255,
            pattern: '^[a-zA-Z0-9](?:[a-zA-Z0-9_.-]{0,253}[a-zA-Z0-9_])?$',
            description: 'Unique node ID used by edges and expressions, for example triage_agent.',
          },
          type: { type: 'string', enum: WEBMCP_WORKFLOW_NODE_TYPES },
          name: { type: 'string', maxLength: 255 },
          parameters: {
            type: 'object',
            additionalProperties: true,
            description:
              'Node parameters in backend format. Examples: script language/code; HTTP method/url/headers/body; agent prompt/model/tool settings; condition condition; loop type for_each or do_while with items or condition; switch cases [{port: case_0, label, condition}] and default_port; wait duration; converge strategy all/any; approval prompt/approvers; AAP template and integration references.',
          },
          settings: { ...NODE_SETTINGS_SCHEMA, description: 'Optional engine settings for this node.' },
        },
      },
    },
    edges: {
      type: 'array',
      minItems: 1,
      maxItems: 100,
      description:
        'Required with nodes. source is a node ID or trigger-0 / trigger-1 by trigger array position; target is a node ID. Use source_handle for branches: true/false, approved/rejected, loop/done, case_0/default. Set target_handle to end for a loop-back edge.',
      items: {
        type: 'object',
        required: ['source', 'target'],
        additionalProperties: false,
        properties: {
          source: { type: 'string', minLength: 1, maxLength: 255 },
          target: { type: 'string', minLength: 1, maxLength: 255 },
          source_handle: {
            type: 'string',
            maxLength: 255,
            pattern: '^(source|loop|true|false|approved|rejected|done|default|case_[0-9]+)$',
          },
          target_handle: { type: 'string', enum: ['target', 'end'] },
        },
      },
    },
  },
}
