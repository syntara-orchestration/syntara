import { describe, expect, it } from 'vitest'

import { convertV2Definition } from './processExistingWorkflow'

describe('convertV2Definition permission redaction', () => {
  it('maps API _permission_redacted to activity metadata', () => {
    const { flattenedActivities } = convertV2Definition(
      [
        {
          id: 'step_1',
          type: 'script',
          name: 'Script',
          _permission_redacted: true,
        } as never,
      ],
      [],
      []
    )

    expect(flattenedActivities[0]?.metadata).toEqual({ __permissionRedacted: true })
  })
})
