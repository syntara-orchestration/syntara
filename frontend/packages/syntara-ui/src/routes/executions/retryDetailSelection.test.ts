import { describe, expect, it } from 'vitest'

import { getRetryDetailSelection } from './retryDetailSelection'

describe('getRetryDetailSelection', () => {
  const activityNameMap = new Map([
    ['selected-step', 'Selected step'],
    ['failed-step', 'Failed step'],
  ])

  it('keeps Run details on a selected step outside the retry plan', () => {
    expect(
      getRetryDetailSelection({
        retryPanelOpen: true,
        selectedStepId: 'selected-step',
        selectedStepName: 'Selected step',
        firstRetryPointId: 'failed-step#attempt-2',
        activityNameMap,
      })
    ).toEqual({ nodeId: 'selected-step', nodeName: 'Selected step' })
  })

  it('uses the first retry point only when there is no selected step', () => {
    expect(
      getRetryDetailSelection({
        retryPanelOpen: true,
        selectedStepId: null,
        selectedStepName: null,
        firstRetryPointId: 'failed-step#iter-2',
        activityNameMap,
      })
    ).toEqual({ nodeId: 'failed-step#iter-2', nodeName: 'Failed step' })
  })

  it('does not replace the selected step when the retry panel is closed', () => {
    expect(
      getRetryDetailSelection({
        retryPanelOpen: false,
        selectedStepId: 'selected-step',
        selectedStepName: 'Selected step',
        firstRetryPointId: 'failed-step#attempt-2',
        activityNameMap,
      })
    ).toEqual({ nodeId: 'selected-step', nodeName: 'Selected step' })
  })
})
