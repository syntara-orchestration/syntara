import { EdgeHandleEnum, TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { buildSwitchCasePort } from '../routes/builder/utils/switchCaseHelpers'

import {
  createAgenticActivity,
  createAAPJobTemplateActivity,
  createAAPWorkflowTemplateActivity,
  createApiActivity,
  createApprovalActivity,
  createConditionActivity,
  createConvergeActivity,
  createEventTrigger,
  createGenericActivity,
  createLoopActivity,
  createManualTrigger,
  createScheduledTrigger,
  createScriptActivity,
  createSwitchActivity,
  createWaitActivity,
  createWebhookTrigger,
  createEdaTrigger,
} from './workflowFactories'

describe('workflowFactories', () => {
  describe('Trigger Factories', () => {
    describe('createManualTrigger', () => {
      it('creates a manual trigger without approval', () => {
        const trigger = createManualTrigger('trigger-1')

        expect(trigger.id).toBe('trigger-1')
        expect(trigger.type).toBe(TriggerTypeEnum.MANUAL_TRIGGER)
        expect(trigger.parameters).toEqual({})
      })

      it('creates a manual trigger with approval param (ignored in v2)', () => {
        const trigger = createManualTrigger('trigger-2', true)

        expect(trigger.id).toBe('trigger-2')
        expect(trigger.type).toBe(TriggerTypeEnum.MANUAL_TRIGGER)
      })

      it('creates a manual trigger with approval false (ignored in v2)', () => {
        const trigger = createManualTrigger('trigger-3', false)

        expect(trigger.id).toBe('trigger-3')
        expect(trigger.type).toBe(TriggerTypeEnum.MANUAL_TRIGGER)
      })

      it('creates a manual trigger with name', () => {
        const trigger = createManualTrigger('trigger-4', undefined, 'My Trigger')

        expect(trigger.id).toBe('trigger-4')
        expect(trigger.type).toBe(TriggerTypeEnum.MANUAL_TRIGGER)
        expect(trigger.name).toBe('My Trigger')
      })

      it('creates a manual trigger with input schema', () => {
        const schema = { type: 'object', properties: { env: { type: 'string' } } }
        const trigger = createManualTrigger('trigger-5', undefined, undefined, schema)

        expect(trigger.parameters.input_schema).toEqual(schema)
      })
    })

    describe('createScheduledTrigger', () => {
      it('creates a cron scheduled trigger', () => {
        const trigger = createScheduledTrigger('trigger-5', 'cron', { cron: '0 9 * * *', timezone: 'UTC' })

        expect(trigger.id).toBe('trigger-5')
        expect(trigger.type).toBe(TriggerTypeEnum.SCHEDULED)
        expect(trigger.parameters.schedule_type).toBe('cron')
        expect(trigger.parameters.cron).toBe('0 9 * * *')
        expect(trigger.parameters.timezone).toBe('UTC')
      })

      it('creates a cron trigger without timezone', () => {
        const trigger = createScheduledTrigger('trigger-6', 'cron', { cron: '0 9 * * *' })

        expect(trigger.id).toBe('trigger-6')
        expect(trigger.parameters.schedule_type).toBe('cron')
        expect(trigger.parameters.cron).toBe('0 9 * * *')
        expect(trigger.parameters).not.toHaveProperty('timezone')
      })

      it('creates an interval scheduled trigger', () => {
        const trigger = createScheduledTrigger('trigger-7', 'interval', { interval: 'PT1H' })

        expect(trigger.id).toBe('trigger-7')
        expect(trigger.type).toBe(TriggerTypeEnum.SCHEDULED)
        expect(trigger.parameters.schedule_type).toBe('interval')
        expect(trigger.parameters.interval).toBe('PT1H')
      })

      it('creates a scheduled trigger with name', () => {
        const trigger = createScheduledTrigger('trigger-9', 'cron', { cron: '0 9 * * *' }, 'Daily Job')

        expect(trigger.id).toBe('trigger-9')
        expect(trigger.name).toBe('Daily Job')
      })

      it('omits cron param when cron config is missing', () => {
        const trigger = createScheduledTrigger('trigger-10', 'cron', {})

        expect(trigger.id).toBe('trigger-10')
        expect(trigger.parameters.schedule_type).toBe('cron')
      })

      it('omits interval param when interval config is missing', () => {
        const trigger = createScheduledTrigger('trigger-11', 'interval', {})

        expect(trigger.id).toBe('trigger-11')
        expect(trigger.parameters.schedule_type).toBe('interval')
      })
    })

    describe('createEventTrigger', () => {
      it('creates an event trigger', () => {
        const trigger = createEventTrigger('trigger-12', 'github', 'push')

        expect(trigger.id).toBe('trigger-12')
        expect(trigger.type).toBe('event')
        expect(trigger.parameters.source).toBe('github')
        expect(trigger.parameters.event_type).toBe('push')
      })

      it('creates an event trigger with filter', () => {
        const trigger = createEventTrigger('trigger-13', 'github', 'push', { branch: 'main' })

        expect(trigger.id).toBe('trigger-13')
        expect(trigger.parameters.filter).toEqual({ branch: 'main' })
      })

      it('creates an event trigger with name', () => {
        const trigger = createEventTrigger('trigger-14', 'github', 'push', undefined, 'GitHub Push')

        expect(trigger.id).toBe('trigger-14')
        expect(trigger.name).toBe('GitHub Push')
      })
    })

    describe('createWebhookTrigger', () => {
      it('creates a webhook trigger with path', () => {
        const trigger = createWebhookTrigger('trigger-20', 'jira-updates')

        expect(trigger.id).toBe('trigger-20')
        expect(trigger.type).toBe(TriggerTypeEnum.WEBHOOK_TRIGGER)
        expect(trigger.name).toBe('Webhook Trigger')
        expect(trigger.parameters.webhook_path).toBe('jira-updates')
        expect(trigger.parameters).not.toHaveProperty('input_schema')
      })

      it('creates a webhook trigger with JSON schema', () => {
        const schema = { type: 'object', properties: { name: { type: 'string' } } }
        const trigger = createWebhookTrigger('trigger-21', 'github-push', schema)

        expect(trigger.id).toBe('trigger-21')
        expect(trigger.parameters.webhook_path).toBe('github-push')
        expect(trigger.parameters.input_schema).toEqual(schema)
      })

      it('creates a webhook trigger with custom name', () => {
        const trigger = createWebhookTrigger('trigger-22', 'slack-events', undefined, 'Slack Webhook')

        expect(trigger.id).toBe('trigger-22')
        expect(trigger.name).toBe('Slack Webhook')
      })

      it('creates trigger with any path (format validation in schema layer)', () => {
        const trigger = createWebhookTrigger('trigger-23', 'api/v2/events')
        expect(trigger.parameters.webhook_path).toBe('api/v2/events')
      })
    })

    describe('createEdaTrigger', () => {
      it('creates an EDA trigger with path', () => {
        const trigger = createEdaTrigger('trigger-30', 'eda-events')

        expect(trigger.id).toBe('trigger-30')
        expect(trigger.type).toBe(TriggerTypeEnum.EDA_TRIGGER)
        expect(trigger.name).toBe('EDA Trigger')
        expect(trigger.parameters.webhook_path).toBe('eda-events')
        expect(trigger.parameters).not.toHaveProperty('input_schema')
      })

      it('creates an EDA trigger with JSON schema', () => {
        const schema = { type: 'object', properties: { name: { type: 'string' } } }
        const trigger = createEdaTrigger('trigger-31', 'eda-push', schema)

        expect(trigger.id).toBe('trigger-31')
        expect(trigger.parameters.webhook_path).toBe('eda-push')
        expect(trigger.parameters.input_schema).toEqual(schema)
      })

      it('creates an EDA trigger with custom name', () => {
        const trigger = createEdaTrigger('trigger-32', 'eda-alerts', undefined, 'My EDA Trigger')

        expect(trigger.id).toBe('trigger-32')
        expect(trigger.name).toBe('My EDA Trigger')
      })

      it('creates trigger with any path (format validation in schema layer)', () => {
        const trigger = createEdaTrigger('trigger-33', 'api/v2/events')
        expect(trigger.parameters.webhook_path).toBe('api/v2/events')
      })
    })
  })

  describe('Activity Factories', () => {
    describe('createScriptActivity', () => {
      it('creates a script activity', () => {
        const activity = createScriptActivity({
          id: 'task-1',
          name: 'My Script',
          language: 'python',
          code: 'print("hello")',
        })

        expect(activity.type).toBe('script')
        expect(activity.id).toBe('task-1')
        expect(activity.name).toBe('My Script')
        expect(activity.parameters.language).toBe('python')
        expect(activity.parameters.code).toBe('print("hello")')
      })

      it('creates a bash script activity', () => {
        const activity = createScriptActivity({
          id: 'task-2',
          name: 'Bash Script',
          language: 'bash',
          code: 'echo hello',
        })

        expect(activity.parameters.language).toBe('bash')
      })

      it('includes credential_id when provided', () => {
        const activity = createScriptActivity({
          id: 'task-3',
          name: 'Script',
          language: 'python',
          code: 'pass',
          credentialId: 'cred-1',
        })

        expect(activity.parameters.credential_id).toBe('cred-1')
      })

      it('includes settings when provided', () => {
        const activity = createScriptActivity({
          id: 'task-4',
          name: 'Script',
          language: 'python',
          code: 'pass',
          settings: { timeout: 300 },
        })

        expect(activity.settings).toEqual({ timeout: 300 })
      })

      it('omits settings when not provided', () => {
        const activity = createScriptActivity({
          id: 'task-5',
          name: 'Script',
          language: 'python',
          code: 'pass',
        })

        expect(activity).not.toHaveProperty('settings')
      })

      it('includes parsed environment when valid JSON provided', () => {
        const activity = createScriptActivity({
          id: 'task-6',
          name: 'Script',
          language: 'python',
          code: 'pass',
          environment: '{"MY_VAR": "hello", "OTHER": "world"}',
        })

        expect(activity.parameters.environment).toEqual({ MY_VAR: 'hello', OTHER: 'world' })
      })

      it('omits environment when not provided', () => {
        const activity = createScriptActivity({
          id: 'task-7',
          name: 'Script',
          language: 'python',
          code: 'pass',
        })

        expect(activity.parameters).not.toHaveProperty('environment')
      })

      it('omits environment when invalid JSON provided', () => {
        const activity = createScriptActivity({
          id: 'task-8',
          name: 'Script',
          language: 'python',
          code: 'pass',
          environment: 'not valid json',
        })

        expect(activity.parameters).not.toHaveProperty('environment')
      })
    })

    describe('createApiActivity', () => {
      it('creates an API activity', () => {
        const activity = createApiActivity({
          id: 'api-1',
          name: 'API Call',
          method: 'GET',
          url: 'https://api.example.com',
        })

        expect(activity.type).toBe('http_request')
        expect(activity.id).toBe('api-1')
        expect(activity.parameters.method).toBe('GET')
        expect(activity.parameters.url).toBe('https://api.example.com')
      })

      it('creates an API activity with headers', () => {
        const activity = createApiActivity({
          id: 'api-1',
          name: 'API Call',
          method: 'POST',
          url: 'https://api.example.com',
          headers: [{ id: 'h1', key: 'Authorization', value: 'Bearer token' }],
        })

        expect(activity.parameters.headers).toEqual({ Authorization: 'Bearer token' })
      })

      it('creates an API activity with body', () => {
        const activity = createApiActivity({
          id: 'api-1',
          name: 'API Call',
          method: 'POST',
          url: 'https://api.example.com',
          body: '{"data": "value"}',
        })

        expect(activity.parameters.body).toEqual({ data: 'value' })
      })

      it('uses string body when JSON parsing fails', () => {
        const activity = createApiActivity({
          id: 'api-1',
          name: 'API Call',
          method: 'POST',
          url: 'https://api.example.com',
          body: 'plain text body',
        })

        expect(activity.parameters.body).toBe('plain text body')
      })

      it('skips header entries with empty keys', () => {
        const activity = createApiActivity({
          id: 'api-1',
          name: 'API Call',
          method: 'GET',
          url: 'https://api.example.com',
          headers: [{ id: 'h1', key: '', value: 'ignored' }],
        })

        expect(activity.parameters.headers).toBeUndefined()
      })

      it('does not include inputs in v2', () => {
        const activity = createApiActivity({
          id: 'api-1',
          name: 'API Call',
          method: 'GET',
          url: 'https://api.example.com',
          inputs: '{"param": "value"}',
        })

        expect(activity.parameters).not.toHaveProperty('inputs')
      })

      it('includes settings when provided', () => {
        const activity = createApiActivity({
          id: 'api-1',
          name: 'API Call',
          method: 'GET',
          url: 'https://api.example.com',
          settings: { timeout: 60 },
        })

        expect(activity.settings).toEqual({ timeout: 60 })
      })

      it('includes credential_id when provided', () => {
        const activity = createApiActivity({
          id: 'api-1',
          name: 'API Call',
          method: 'GET',
          url: 'https://api.example.com',
          credentialId: 'cred-abc',
        })

        expect(activity.parameters.credential_id).toBe('cred-abc')
      })
    })

    describe('createAgenticActivity', () => {
      it('creates an agentic activity', () => {
        const activity = createAgenticActivity({ id: 'agent-1', name: 'Task Agent' })

        expect(activity.type).toBe('agentic')
        expect(activity.id).toBe('agent-1')
        expect(activity.parameters).toEqual({})
      })

      it('creates an agentic activity with ALL strategy', () => {
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          toolSelectionStrategy: 'ALL',
        })

        expect(activity.parameters.tool_selection_strategy).toBe('ALL')
        expect(activity.parameters.tool_selections).toBeUndefined()
      })

      it('creates an agentic activity with SELECTED strategy and tool IDs', () => {
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          toolSelectionStrategy: 'SELECTED',
          toolSelections: ['tool1', 'tool2'],
        })

        expect(activity.parameters.tool_selections).toEqual(['tool1', 'tool2'])
        expect(activity.parameters.tool_selection_strategy).toBe('SELECTED')
      })

      it('creates an agentic activity with NONE strategy', () => {
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          toolSelectionStrategy: 'NONE',
        })

        expect(activity.parameters.tool_selection_strategy).toBe('NONE')
        expect(activity.parameters.tool_selections).toBeUndefined()
      })

      it('creates an agentic activity with prompt', () => {
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          prompt: 'Do something',
        })

        expect(activity.parameters.prompt).toBe('Do something')
      })

      it('creates an agentic activity with llmModelId', () => {
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          llmModelId: '550e8400-e29b-41d4-a716-446655440000',
        })

        expect(activity.parameters.llm_model_id).toBe('550e8400-e29b-41d4-a716-446655440000')
      })

      it('creates an agentic activity with fileIds', () => {
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          fileIds: ['file-1', 'file-2'],
        })

        expect(activity.parameters.file_ids).toEqual(['file-1', 'file-2'])
      })

      it('does not include tool strategy when toolSelectionStrategy is undefined', () => {
        const activity = createAgenticActivity({ id: 'agent-1', name: 'Task Agent' })

        expect(activity.parameters.tool_selections).toBeUndefined()
        expect(activity.parameters.tool_selection_strategy).toBeUndefined()
      })

      it('includes integration_connections when provided', () => {
        const connections = [
          { integration_id: 'int-1', credential_id: 'cred-1' },
          { integration_id: 'int-2', credential_id: 'cred-2' },
        ]
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          integrationConnections: connections,
        })

        expect(activity.parameters.integration_connections).toEqual(connections)
      })

      it('does not include integration_connections when empty', () => {
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          integrationConnections: [],
        })

        expect(activity.parameters).not.toHaveProperty('integration_connections')
      })

      it('does not include integration_connections when undefined', () => {
        const activity = createAgenticActivity({ id: 'agent-1', name: 'Task Agent' })

        expect(activity.parameters).not.toHaveProperty('integration_connections')
      })

      it('does not include inputs in v2', () => {
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          inputs: '{"key": "val"}',
        })

        expect(activity.parameters).not.toHaveProperty('inputs')
      })

      it('includes settings when provided', () => {
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          settings: { timeout: 600, continue_on_failure: true },
        })

        expect(activity.settings).toEqual({ timeout: 600, continue_on_failure: true })
      })

      it('includes credentialId and responseSchema', () => {
        const schema = { type: 'object', properties: { result: { type: 'string' } } }
        const activity = createAgenticActivity({
          id: 'agent-1',
          name: 'Task Agent',
          credentialId: 'cred-1',
          responseSchema: schema,
        })

        expect(activity.parameters.credential_id).toBe('cred-1')
        expect(activity.parameters.response_schema).toEqual(schema)
      })

      it('does not include empty fileIds array', () => {
        const activity = createAgenticActivity({ id: 'agent-1', name: 'Task Agent', fileIds: [] })

        expect(activity.parameters.file_ids).toBeUndefined()
      })
    })

    describe('createConditionActivity', () => {
      it('creates a condition activity', () => {
        const activity = createConditionActivity('cond-1', 'Check Status', 'status === "active"')

        expect(activity.type).toBe('condition')
        expect(activity.id).toBe('cond-1')
        expect(activity.name).toBe('Check Status')
        expect(activity.parameters.condition).toBe('status === "active"')
      })
    })

    describe('createLoopActivity', () => {
      it('creates a forEach loop activity', () => {
        const activity = createLoopActivity('loop-1', 'Process Items', 'forEach', {
          items: '{{ items }}',
          itemVariable: 'item',
          indexVariable: 'idx',
        })

        expect(activity.type).toBe('loop')
        expect(activity.id).toBe('loop-1')
        expect(activity.parameters.type).toBe('for_each')
        expect(activity.parameters.items).toBe('{{ items }}')
      })

      it('creates a while loop activity', () => {
        const activity = createLoopActivity('loop-1', 'While Loop', 'while', {
          condition: 'count < 10',
          maxIterations: 100,
        })

        expect(activity.parameters.type).toBe('do_while')
        expect(activity.parameters.condition).toBe('count < 10')
        expect(activity.parameters.max_iterations).toBe(100)
      })

      it('does not include invalid maxIterations', () => {
        const activity = createLoopActivity('loop-1', 'While Loop', 'while', {
          condition: 'count < 10',
          maxIterations: Number.NaN,
        })

        expect(activity.parameters).not.toHaveProperty('max_iterations')
      })

      it('omits items when config is missing', () => {
        const activity = createLoopActivity('loop-1', 'Loop', 'forEach', {})

        expect(activity.parameters.type).toBe('for_each')
        expect(activity.parameters).not.toHaveProperty('items')
      })

      it('omits condition when config is missing', () => {
        const activity = createLoopActivity('loop-1', 'Loop', 'while', {})

        expect(activity.parameters.type).toBe('do_while')
        expect(activity.parameters).not.toHaveProperty('condition')
      })

      it('includes settings when provided', () => {
        const activity = createLoopActivity('loop-1', 'Loop', 'forEach', { items: '{{ list }}' }, { timeout: 300 })

        expect(activity.settings).toEqual({ timeout: 300 })
      })

      it('includes max_iterations for forEach', () => {
        const activity = createLoopActivity('loop-1', 'Loop', 'forEach', { items: '{{ list }}', maxIterations: 50 })

        expect(activity.parameters.max_iterations).toBe(50)
      })
    })

    describe('createConvergeActivity', () => {
      it('creates a converge activity', () => {
        const activity = createConvergeActivity('conv-1', 'Wait for All')

        expect(activity.type).toBe('converge')
        expect(activity.id).toBe('conv-1')
        expect(activity.name).toBe('Wait for All')
        expect(activity.parameters.strategy).toBe('all')
      })

      it('creates a converge activity with config', () => {
        const activity = createConvergeActivity('conv-1', 'Converge', { strategy: 'all' })

        expect(activity.parameters.strategy).toBe('all')
      })

      it('creates a converge activity with strategy', () => {
        const activity = createConvergeActivity('conv-1', 'Converge', {
          strategy: 'any',
        })

        expect(activity.parameters.strategy).toBe('any')
      })

      it('creates a converge activity with strategy any and n_required', () => {
        const activity = createConvergeActivity('conv-1', 'Converge Any', {
          strategy: 'any',
          requiredPathCount: 2,
        })

        expect(activity.parameters.strategy).toBe('any')
        expect(activity.parameters.n_required).toBe(2)
      })

      it('includes settings when provided', () => {
        const activity = createConvergeActivity('conv-1', 'Converge', { strategy: 'all' }, { timeout: 600 })

        expect(activity.settings).toEqual({ timeout: 600 })
      })

      it('includes wait_duration when provided', () => {
        const activity = createConvergeActivity('conv-1', 'Converge', { strategy: 'all', wait_duration: 120 })

        expect(activity.parameters.wait_duration).toBe(120)
      })

      it('does not include n_required for strategy all', () => {
        const activity = createConvergeActivity('conv-1', 'Converge', { strategy: 'all', requiredPathCount: 2 })

        expect(activity.parameters).not.toHaveProperty('n_required')
      })
    })

    describe('createAAPJobTemplateActivity', () => {
      it('creates an AAP job template activity', () => {
        const activity = createAAPJobTemplateActivity('aap-1', 'Run Playbook', 123)

        expect(activity.type).toBe('aap_job_template')
        expect(activity.id).toBe('aap-1')
        expect(activity.parameters.job_template_id).toBe(123)
      })

      it('creates an AAP activity with full config', () => {
        const activity = createAAPJobTemplateActivity('aap-1', 'Run Playbook', 123, {
          inventory: 456,
          extraVars: { env: 'prod' },
          limit: 'web-servers',
          tags: 'deploy',
          skipTags: 'test',
          verbosity: 2,
          jobType: 'run',
          forks: 10,
          jobSlicing: 2,
          diffMode: true,
        })

        expect(activity.parameters.inventory_id).toBe(456)
        expect(activity.parameters.extra_vars).toEqual({ env: 'prod' })
        expect(activity.parameters.limit).toBe('web-servers')
        expect(activity.parameters.tags).toBe('deploy')
        expect(activity.parameters.skip_tags).toBe('test')
        expect(activity.parameters.verbosity).toBe(2)
        expect(activity.parameters.job_type).toBe('run')
        expect(activity.parameters.forks).toBe(10)
        expect(activity.parameters.job_slice_count).toBe(2)
        expect(activity.parameters.diff_mode).toBe(true)
      })

      it('includes integration_id when integrationId is set in config', () => {
        const activity = createAAPJobTemplateActivity('aap-1', 'Run Playbook', 123, {
          integrationId: 'int-aap-1',
        })

        expect(activity.parameters.integration_id).toBe('int-aap-1')
      })

      it('omits integration_id when integrationId is empty string', () => {
        const activity = createAAPJobTemplateActivity('aap-1', 'Run Playbook', 123, {
          integrationId: '',
        })

        expect(activity.parameters).not.toHaveProperty('integration_id')
      })

      it('includes both credential_id and integration_id when both set', () => {
        const activity = createAAPJobTemplateActivity('aap-1', 'Run Playbook', 123, {
          credentialId: 'cred-123',
          integrationId: 'int-aap-1',
        })

        expect(activity.parameters.credential_id).toBe('cred-123')
        expect(activity.parameters.integration_id).toBe('int-aap-1')
      })
    })

    describe('createAAPWorkflowTemplateActivity', () => {
      it('creates an AAP workflow template activity', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456)

        expect(activity.type).toBe('aap_workflow_job_template')
        expect(activity.id).toBe('aap-wf-1')
        expect(activity.parameters.workflow_job_template_id).toBe(456)
      })

      it('creates an AAP workflow template activity with full config', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          inventory_id: 789,
          extra_vars: { env: 'staging' },
          limit: 'db-servers',
          scm_branch: 'main',
          tags: 'deploy',
          skip_tags: 'debug',
          labels: ['production', 'critical'],
        })

        expect(activity.parameters.workflow_job_template_id).toBe(456)
        expect(activity.parameters.inventory_id).toBe(789)
        expect(activity.parameters.extra_vars).toEqual({ env: 'staging' })
        expect(activity.parameters.limit).toBe('db-servers')
        expect(activity.parameters.scm_branch).toBe('main')
        expect(activity.parameters.tags).toBe('deploy')
        expect(activity.parameters.skip_tags).toBe('debug')
        expect(activity.parameters.labels).toEqual(['production', 'critical'])
      })

      it('creates an AAP workflow template activity with credential and organization', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          credential_id: 'cred-123',
          organization_id: 10,
          organization_name: 'Engineering',
        })

        expect(activity.parameters.credential_id).toBe('cred-123')
        expect(activity.parameters.organization_id).toBe(10)
        expect(activity.parameters.organization_name).toBe('Engineering')
      })

      it('includes integration_id when set in workflow config', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          integration_id: 'int-aap-2',
        })

        expect(activity.parameters.integration_id).toBe('int-aap-2')
      })

      it('includes both credential_id and integration_id in workflow config', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          credential_id: 'cred-xyz',
          integration_id: 'int-aap-3',
        })

        expect(activity.parameters.credential_id).toBe('cred-xyz')
        expect(activity.parameters.integration_id).toBe('int-aap-3')
      })

      it('creates an AAP workflow template activity with inventory name', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          inventory_name: 'Production Inventory',
        })

        expect(activity.parameters.inventory_name).toBe('Production Inventory')
      })

      it('creates an AAP workflow template activity with workflow job template name', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          workflow_job_template_name: 'Deploy Application',
        })

        expect(activity.parameters.workflow_job_template_name).toBe('Deploy Application')
      })

      it('does not include job-specific fields (job_type, verbosity, forks, etc.)', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          inventory_id: 789,
          extra_vars: { env: 'prod' },
        })

        // Workflow templates should NOT have job-specific fields
        expect(activity.parameters).not.toHaveProperty('job_type')
        expect(activity.parameters).not.toHaveProperty('verbosity')
        expect(activity.parameters).not.toHaveProperty('forks')
        expect(activity.parameters).not.toHaveProperty('timeout')
        expect(activity.parameters).not.toHaveProperty('job_slice_count')
        expect(activity.parameters).not.toHaveProperty('diff_mode')
        expect(activity.parameters).not.toHaveProperty('execution_environment')
        expect(activity.parameters).not.toHaveProperty('execution_environment_id')
        expect(activity.parameters).not.toHaveProperty('instance_group_id')
        expect(activity.parameters).not.toHaveProperty('instance_group_name')
        expect(activity.parameters).not.toHaveProperty('job_credentials')
      })

      it('includes scm_branch field (workflow-specific)', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          scm_branch: 'feature/new-deployment',
        })

        expect(activity.parameters.scm_branch).toBe('feature/new-deployment')
      })

      it('filters undefined values correctly', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          inventory_id: undefined,
          extra_vars: undefined,
          limit: undefined,
        })

        expect(activity.parameters).not.toHaveProperty('inventory_id')
        expect(activity.parameters).not.toHaveProperty('extra_vars')
        expect(activity.parameters).not.toHaveProperty('limit')
      })

      it('handles numeric zero values correctly (defined predicate)', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          inventory_id: 0,
          organization_id: 0,
        })

        // Zero is a valid value for numeric fields (defined predicate)
        expect(activity.parameters.inventory_id).toBe(0)
        expect(activity.parameters.organization_id).toBe(0)
      })

      it('filters invalid numeric values (NaN, Infinity)', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          inventory_id: Number.NaN,
          organization_id: Number.POSITIVE_INFINITY,
        })

        expect(activity.parameters).not.toHaveProperty('inventory_id')
        expect(activity.parameters).not.toHaveProperty('organization_id')
      })

      it('filters empty strings for truthy predicate fields', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          organization_name: '',
          workflow_job_template_name: '',
          limit: '',
        })

        expect(activity.parameters).not.toHaveProperty('organization_name')
        expect(activity.parameters).not.toHaveProperty('workflow_job_template_name')
        expect(activity.parameters).not.toHaveProperty('limit')
      })

      it('includes empty arrays for labels field', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          labels: [],
        })

        // Empty array is still truthy in JavaScript (all objects are truthy)
        expect(activity.parameters.labels).toEqual([])
      })

      it('includes non-empty arrays for labels field', () => {
        const activity = createAAPWorkflowTemplateActivity('aap-wf-1', 'Run Workflow', 456, {
          labels: ['production'],
        })

        expect(activity.parameters.labels).toEqual(['production'])
      })
    })

    describe('createWaitActivity', () => {
      it('creates a wait activity with duration', () => {
        const activity = createWaitActivity('wait-1', 'Wait 5 min', { duration: 300 })

        expect(activity.type).toBe('wait')
        expect(activity.id).toBe('wait-1')
        expect(activity.name).toBe('Wait 5 min')
        expect(activity.parameters).toEqual({ duration: 300 })
      })

      it('creates a wait activity with zero duration', () => {
        const activity = createWaitActivity('wait-2', 'No Wait', { duration: 0 })

        expect(activity.type).toBe('wait')
        expect(activity.parameters).toEqual({ duration: 0 })
      })

      it('includes settings when provided', () => {
        const activity = createWaitActivity('wait-3', 'Wait', { duration: 60 }, { continue_on_failure: true })

        expect(activity.settings).toEqual({ continue_on_failure: true })
      })
    })

    describe('createGenericActivity', () => {
      it('creates a generic placeholder activity', () => {
        const activity = createGenericActivity('gen-1')

        expect(activity.type).toBe('generic')
        expect(activity.id).toBe('gen-1')
        expect(activity.name).toBe('New Step')
        expect((activity.metadata as { __isGeneric?: boolean })?.__isGeneric).toBe(true)
      })

      it('creates a generic activity with custom name', () => {
        const activity = createGenericActivity('gen-1', 'Custom Name')

        expect(activity.name).toBe('Custom Name')
      })

      it('creates a generic activity with custom message', () => {
        const activity = createGenericActivity('gen-1', 'Step', 'Select a node type')

        expect((activity.metadata as { __customMessage?: string })?.__customMessage).toBe('Select a node type')
      })
    })

    describe('createApprovalActivity', () => {
      it('creates an approval activity', () => {
        const activity = createApprovalActivity({
          id: 'appr-1',
          name: 'Approval Gate',
          approver_users: ['admin@example.com'],
          prompt: 'Please approve',
        })

        expect(activity.type).toBe('approval')
        expect(activity.id).toBe('appr-1')
        expect(activity.name).toBe('Approval Gate')
        expect(activity.parameters).toEqual({
          prompt: 'Please approve',
          approver_users: ['admin@example.com'],
        })
      })

      it('passes settings when provided', () => {
        const activity = createApprovalActivity({
          id: 'appr-1',
          name: 'Approval',
          approver_users: ['admin@example.com'],
          prompt: 'Approve?',
          settings: { timeout: 7200, continue_on_failure: true },
        })

        expect(activity.settings).toEqual({ timeout: 7200, continue_on_failure: true })
        expect(activity.parameters.prompt).toBe('Approve?')
        expect(activity.parameters.approver_users).toEqual(['admin@example.com'])
      })

      it('includes fallback_decision and decision_window', () => {
        const activity = createApprovalActivity({
          id: 'appr-2',
          name: 'Approval',
          approver_users: ['admin@example.com'],
          prompt: 'Approve?',
          fallback_decision: 'reject',
          decision_window: 86400,
        })

        expect(activity.parameters.fallback_decision).toBe('reject')
        expect(activity.parameters.decision_window).toBe(86400)
      })

      it('omits settings when not provided', () => {
        const activity = createApprovalActivity({
          id: 'appr-3',
          name: 'Approval',
          approver_users: ['admin@example.com'],
          prompt: 'Approve?',
        })

        expect(activity).not.toHaveProperty('settings')
      })

      it('includes approver_groups', () => {
        const activity = createApprovalActivity({
          id: 'appr-4',
          name: 'Approval',
          approver_groups: ['admins', 'deployers'],
          prompt: 'Approve?',
        })

        expect(activity.parameters.approver_groups).toEqual(['admins', 'deployers'])
      })
    })

    describe('createSwitchActivity', () => {
      it('creates a switch activity with correct type and config', () => {
        const cases = [
          { port: buildSwitchCasePort(0), label: 'Path 1', condition: '${status} == "active"' },
          { port: buildSwitchCasePort(1), label: 'Path 2', condition: '${status} == "inactive"' },
        ]
        const activity = createSwitchActivity('switch-1', 'Route Request', cases)

        expect(activity.id).toBe('switch-1')
        expect(activity.type).toBe('switch')
        expect(activity.name).toBe('Route Request')
        expect(activity.parameters).toEqual({
          cases,
          default_port: EdgeHandleEnum.DEFAULT,
        })
      })

      it('creates a switch activity with empty cases', () => {
        const activity = createSwitchActivity('switch-2', 'Empty Switch', [])

        expect(activity.parameters.cases).toEqual([])
        expect(activity.parameters.default_port).toBe(EdgeHandleEnum.DEFAULT)
      })
    })
  })
})
