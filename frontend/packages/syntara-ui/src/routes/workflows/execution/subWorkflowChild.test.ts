import { describe, expect, it } from 'vitest'

import { extractSubWorkflowChild } from './subWorkflowChild'

describe('extractSubWorkflowChild', () => {
  it('reads the child reference from runtimeMetadata while the child runs (no output yet)', () => {
    expect(
      extractSubWorkflowChild({ child_execution_id: 'child-live', child_workflow_name: 'Live Child' }, null)
    ).toEqual({ childExecutionId: 'child-live', childName: 'Live Child' })
  })

  it('falls back to outputData once the child is terminal and runtimeMetadata is absent', () => {
    expect(extractSubWorkflowChild(null, { child_execution_id: 'child-done', workflow_name: 'Done Child' })).toEqual({
      childExecutionId: 'child-done',
      childName: 'Done Child',
    })
  })

  it('prefers runtimeMetadata when both sources carry a child reference', () => {
    expect(
      extractSubWorkflowChild(
        { child_execution_id: 'child-live', child_workflow_name: 'Live Child' },
        { child_execution_id: 'child-done', workflow_name: 'Done Child' }
      )
    ).toEqual({ childExecutionId: 'child-live', childName: 'Live Child' })
  })

  it('falls back to outputData when runtimeMetadata has no usable child_execution_id', () => {
    expect(
      extractSubWorkflowChild(
        { child_workflow_name: 'No Id Yet' },
        { child_execution_id: 'child-done', workflow_name: 'Done Child' }
      )
    ).toEqual({ childExecutionId: 'child-done', childName: 'Done Child' })
  })

  it('resolves for_each nodes from outputData (runtime metadata not populated for for_each)', () => {
    expect(extractSubWorkflowChild(null, { child_execution_id: 'child-iter', workflow_name: 'Iter Child' })).toEqual({
      childExecutionId: 'child-iter',
      childName: 'Iter Child',
    })
  })

  it('returns a null name when the resolved source omits the name field', () => {
    expect(extractSubWorkflowChild({ child_execution_id: 'child-live' }, null)).toEqual({
      childExecutionId: 'child-live',
      childName: null,
    })
  })

  it('returns null when neither source has a usable child reference', () => {
    expect(extractSubWorkflowChild(null, null)).toBeNull()
    expect(extractSubWorkflowChild(undefined, undefined)).toBeNull()
    expect(extractSubWorkflowChild({}, {})).toBeNull()
    expect(extractSubWorkflowChild({ child_execution_id: '' }, { child_execution_id: '' })).toBeNull()
  })
})
