import { describe, expect, it } from 'vitest'

import * as routeRefs from '../../app/routes/routeReferences'

import { buildWorkflowBuilderLink } from './buildWorkflowBuilderLink'

describe('buildWorkflowBuilderLink', () => {
  it('includes the version query param when version is provided', () => {
    expect(buildWorkflowBuilderLink('wf-1', 3)).toEqual({
      to: routeRefs.builderEditRoute.fullPath,
      params: { workflowId: 'wf-1' },
      search: { version: '3' },
    })
  })

  it('omits the version query param when version is null', () => {
    expect(buildWorkflowBuilderLink('wf-1', null)).toEqual({
      to: routeRefs.builderEditRoute.fullPath,
      params: { workflowId: 'wf-1' },
    })
  })

  it('omits the version query param when version is undefined', () => {
    expect(buildWorkflowBuilderLink('wf-1', undefined)).toEqual({
      to: routeRefs.builderEditRoute.fullPath,
      params: { workflowId: 'wf-1' },
    })
  })

  it('treats version 0 as a valid version', () => {
    expect(buildWorkflowBuilderLink('wf-1', 0)).toEqual({
      to: routeRefs.builderEditRoute.fullPath,
      params: { workflowId: 'wf-1' },
      search: { version: '0' },
    })
  })
})
