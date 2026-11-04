import { describe, expect, it } from 'vitest'

import { workflowListRunConfirmVisible, workflowListRunPreparingCandidate } from './workflowListRunResolutionUi'

describe('workflowListRunResolutionUi', () => {
  const baseState = {
    runDialogOpen: true,
    hasWorkflow: true,
    isResolvingRun: true,
    runConfirmVisible: false,
    hasPendingRunInput: false,
    formStepSelectVisible: false,
  }

  describe('workflowListRunPreparingCandidate', () => {
    it('is true while resolving before confirm or form input', () => {
      expect(workflowListRunPreparingCandidate(baseState)).toBe(true)
    })

    it('is false when the run dialog is closed', () => {
      expect(workflowListRunPreparingCandidate({ ...baseState, runDialogOpen: false })).toBe(false)
    })

    it('is false once the confirm step is shown', () => {
      expect(workflowListRunPreparingCandidate({ ...baseState, runConfirmVisible: true })).toBe(false)
    })

    it('is false while a form or JSON input dialog is open', () => {
      expect(workflowListRunPreparingCandidate({ ...baseState, hasPendingRunInput: true })).toBe(false)
    })

    it('is false while the form step selector is visible', () => {
      expect(workflowListRunPreparingCandidate({ ...baseState, formStepSelectVisible: true })).toBe(false)
    })

    it('is false after resolution finishes', () => {
      expect(workflowListRunPreparingCandidate({ ...baseState, isResolvingRun: false })).toBe(false)
    })
  })

  describe('workflowListRunConfirmVisible', () => {
    it('requires both an open dialog and a resolved confirm step', () => {
      expect(workflowListRunConfirmVisible(true, true)).toBe(true)
      expect(workflowListRunConfirmVisible(true, false)).toBe(false)
      expect(workflowListRunConfirmVisible(false, true)).toBe(false)
    })
  })
})
