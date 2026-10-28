import { TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { WorkflowRunTrigger } from '../resolveWorkflowRunTrigger'

import {
  formTriggerRequiresInputCollection,
  isFormTriggerType,
  readFormTriggerPresentation,
  workflowRunSkipsManualRunConfirmation,
  workflowRunTriggerRequiresInputCollection,
} from './formTriggerRunUtils'

describe('formTriggerRunUtils', () => {
  describe('isFormTriggerType', () => {
    it('returns true for form_trigger', () => {
      expect(isFormTriggerType(TriggerTypeEnum.FORM_TRIGGER)).toBe(true)
    })

    it('returns false for other trigger types', () => {
      expect(isFormTriggerType(TriggerTypeEnum.MANUAL_TRIGGER)).toBe(false)
      expect(isFormTriggerType(undefined)).toBe(false)
    })
  })

  describe('readFormTriggerPresentation', () => {
    it('returns undefined when form_definition is missing', () => {
      expect(readFormTriggerPresentation({ message: 'hi' })).toBeUndefined()
    })

    it('returns undefined for invalid form_definition', () => {
      expect(readFormTriggerPresentation({ form_definition: { fields: 'not-an-array' } })).toBeUndefined()
    })

    it('maps trigger parameters to presentation fields', () => {
      const result = readFormTriggerPresentation({
        form_definition: {
          fields: [{ type: 'text', value_name: 'notes', label: 'Notes', required: false }],
        },
        message: 'Please complete',
        submit_label: 'Go',
        success_message: 'Thanks',
        css_override: '.x {}',
      })

      expect(result).toEqual({
        definition: {
          fields: [{ type: 'text', value_name: 'notes', label: 'Notes', required: false }],
        },
        message: 'Please complete',
        submitLabel: 'Go',
        successMessage: 'Thanks',
        cssOverride: '.x {}',
      })
    })
  })

  describe('formTriggerRequiresInputCollection', () => {
    it('returns false when form trigger is missing or has no fields', () => {
      expect(formTriggerRequiresInputCollection(undefined)).toBe(false)
      expect(
        formTriggerRequiresInputCollection({
          definition: { fields: [] },
        })
      ).toBe(false)
    })

    it('returns true when the form has at least one field', () => {
      expect(
        formTriggerRequiresInputCollection({
          definition: {
            fields: [{ type: 'text', value_name: 'x', label: 'X', required: true }],
          },
        })
      ).toBe(true)
    })
  })

  describe('workflowRunTriggerRequiresInputCollection', () => {
    const baseTrigger = (overrides: Partial<WorkflowRunTrigger>): WorkflowRunTrigger => ({
      triggerNodeId: 't1',
      triggerName: 'Trigger',
      hasTriggerReferences: false,
      ...overrides,
    })

    it('uses form field count for form triggers', () => {
      expect(
        workflowRunTriggerRequiresInputCollection(
          baseTrigger({
            triggerType: TriggerTypeEnum.FORM_TRIGGER,
            formTrigger: { definition: { fields: [{ type: 'text', value_name: 'a', label: 'A', required: true }] } },
          })
        )
      ).toBe(true)
    })

    it('does not require JSON input collection for form triggers with fields', () => {
      expect(
        workflowRunTriggerRequiresInputCollection(
          baseTrigger({
            triggerType: TriggerTypeEnum.FORM_TRIGGER,
            formTrigger: { definition: { fields: [{ type: 'text', value_name: 'a', label: 'A', required: true }] } },
            hasTriggerReferences: true,
            inputSchema: { type: 'object', properties: { x: { type: 'string' } } },
          })
        )
      ).toBe(true)
    })

    it('falls back to manual trigger rules for non-form triggers', () => {
      expect(
        workflowRunTriggerRequiresInputCollection(
          baseTrigger({
            triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
            inputSchema: { type: 'object', properties: { x: { type: 'string' } } },
          })
        )
      ).toBe(true)
    })
  })

  describe('workflowRunSkipsManualRunConfirmation', () => {
    it('skips confirmation when a valid form trigger is present', () => {
      expect(
        workflowRunSkipsManualRunConfirmation({
          triggerNodeId: 'form',
          triggerName: 'Form',
          hasTriggerReferences: false,
          triggerType: TriggerTypeEnum.FORM_TRIGGER,
          formTrigger: { definition: { fields: [{ type: 'text', value_name: 'a', label: 'A', required: true }] } },
        })
      ).toBe(true)
    })

    it('does not skip when form trigger type lacks presentation', () => {
      expect(
        workflowRunSkipsManualRunConfirmation({
          triggerNodeId: 'form',
          triggerName: 'Form',
          hasTriggerReferences: false,
          triggerType: TriggerTypeEnum.FORM_TRIGGER,
        })
      ).toBe(false)
    })
  })
})
