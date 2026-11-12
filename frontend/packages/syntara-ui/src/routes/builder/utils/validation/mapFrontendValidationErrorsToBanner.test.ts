import { ActivityTypeEnum } from '@syntara/contracts'
import { beforeEach, describe, expect, it } from 'vitest'

import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../../../stores/workflowStoreTypes'

import {
  countBlockingValidationErrors,
  filterFrontendFormDefinitionErrorsCoveredByBackend,
  lookupFormFieldLabel,
  mapUtilsValidationErrorsToBanner,
} from './mapFrontendValidationErrorsToBanner'
import type { ValidationError as UtilsValidationError } from './types'

beforeEach(() => {
  useWorkflowStore.getState().setWorkflow(null)
})

describe('lookupFormFieldLabel', () => {
  it('looks up the authored label for a form-definition field path', () => {
    const workflow: WorkflowDefinition = {
      schema_version: '2.0.0',
      name: 'Test workflow',
      description: '',
      triggers: [],
      workflow: {
        activities: [
          {
            id: 'form-1',
            type: ActivityTypeEnum.FORM_PROMPT,
            name: 'Intake form',
            parameters: {
              form_definition: {
                fields: [{ type: 'text', value_name: 'notes', label: 'Deployment notes' }],
              },
            },
          },
        ],
      },
    }
    useWorkflowStore.getState().setWorkflow(workflow)

    expect(lookupFormFieldLabel('form-1', 'parameters.form_definition.fields.0.type')).toBe('Deployment notes')
  })
})

describe('mapUtilsValidationErrorsToBanner', () => {
  it('maps utils validation errors to banner shape', () => {
    const errors: UtilsValidationError[] = [
      {
        id: 'e1',
        severity: 'error',
        rule: 'minimum-workflow-no-connection',
        message: 'Workflow must have at least one connection between trigger and steps',
      },
    ]

    expect(mapUtilsValidationErrorsToBanner(errors)).toEqual([
      {
        message: errors[0].message,
        nodeId: null,
        nodeName: undefined,
        severity: 'error',
        rule: 'minimum-workflow-no-connection',
      },
    ])
  })
})

describe('filterFrontendFormDefinitionErrorsCoveredByBackend', () => {
  it('drops overlapping form canvas errors when backend reported form_definition findings on the same node', () => {
    const frontend: UtilsValidationError[] = [
      {
        id: 'fe-1',
        severity: 'error',
        rule: 'form-prompt-form-definition',
        message: 'Form "Survey": Field 1 — Value name is required',
        nodeId: 'form-1',
      },
      {
        id: 'fe-2',
        severity: 'error',
        rule: 'minimum-workflow-no-connection',
        message: 'Workflow must have at least one connection between trigger and steps',
      },
    ]
    const backend = [
      {
        message: 'String should match pattern',
        nodeId: 'form-1',
        severity: 'error' as const,
        fieldPath: 'parameters.form_definition.fields.0.value_name',
      },
    ]

    expect(filterFrontendFormDefinitionErrorsCoveredByBackend(frontend, backend)).toEqual([frontend[1]])
  })
})

describe('countBlockingValidationErrors', () => {
  it('counts only non-warning banner errors', () => {
    expect(
      countBlockingValidationErrors([
        { message: 'a', nodeId: null, severity: 'error' },
        { message: 'b', nodeId: null, severity: 'warning' },
      ])
    ).toBe(1)
  })
})
