import { describe, expect, it } from 'vitest'

import { executorMetadata, nodeMetadata, type NodeMetadata } from './nodeMetadata'
import { executorMetadata as stepExecutorMetadata, stepMetadata } from './stepMetadata'
import type { StepMetadata } from './stepMetadata'

describe('legacy node metadata exports', () => {
  it('re-exports the step metadata and shared executor metadata', () => {
    expect(nodeMetadata).toBe(stepMetadata)
    expect(executorMetadata).toBe(stepExecutorMetadata)
  })

  it('preserves the legacy metadata type', () => {
    const nodeEntry: NodeMetadata = nodeMetadata.task
    const stepEntry: StepMetadata = nodeEntry

    expect(stepEntry).toBe(stepMetadata.task)
  })
})
