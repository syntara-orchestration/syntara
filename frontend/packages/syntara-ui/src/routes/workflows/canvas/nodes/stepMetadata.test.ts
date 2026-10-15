import { describe, expect, it, vi } from 'vitest'

vi.mock('../../../../assets/eda.svg?react', () => ({
  default: () => 'EdaIcon',
}))

import { executorMetadata, stepMetadata, type StepMetadata } from './stepMetadata'

describe('stepMetadata', () => {
  describe('step types', () => {
    it('has metadata for trigger node', () => {
      expect(stepMetadata.trigger).toBeDefined()
      expect(stepMetadata.trigger.label).toBe('Trigger')
      expect(stepMetadata.trigger.disableTarget).toBe(true)
      expect(stepMetadata.trigger.expandable).toBe(false)
    })

    it('has metadata for scheduledTrigger node', () => {
      expect(stepMetadata.scheduledTrigger).toBeDefined()
      expect(stepMetadata.scheduledTrigger.label).toBe('Trigger')
      expect(stepMetadata.scheduledTrigger.disableTarget).toBe(true)
      expect(stepMetadata.scheduledTrigger.expandable).toBe(false)
    })

    it('has metadata for task node', () => {
      expect(stepMetadata.task).toBeDefined()
      expect(stepMetadata.task.label).toBe('Task')
      expect(stepMetadata.task.expandable).toBe(true)
    })

    it('has metadata for condition node', () => {
      expect(stepMetadata.condition).toBeDefined()
      expect(stepMetadata.condition.label).toBe('Condition')
      expect(stepMetadata.condition.expandable).toBe(false)
      expect(stepMetadata.condition.icon).toBeDefined()
    })

    it('has metadata for approval node', () => {
      expect(stepMetadata.approval).toBeDefined()
      expect(stepMetadata.approval.label).toBe('Approval')
      expect(stepMetadata.approval.expandable).toBe(false)
      expect(stepMetadata.approval.icon).toBeDefined()
    })

    it('has metadata for loop node', () => {
      expect(stepMetadata.loop).toBeDefined()
      expect(stepMetadata.loop.label).toBe('Loop')
      expect(stepMetadata.loop.enableEnd).toBe(true)
      expect(stepMetadata.loop.expandable).toBe(false)
      expect(stepMetadata.loop.icon).toBeDefined()
    })

    it('has metadata for converge node', () => {
      expect(stepMetadata.converge).toBeDefined()
      expect(stepMetadata.converge.label).toBe('Converge')
      expect(stepMetadata.converge.expandable).toBe(false)
      expect(stepMetadata.converge.icon).toBeDefined()
    })
  })

  describe('node metadata structure', () => {
    it('all step types have required label field', () => {
      Object.entries(stepMetadata).forEach(([, metadata]) => {
        expect(metadata.label).toBeDefined()
        expect(typeof metadata.label).toBe('string')
        expect(metadata.label.length).toBeGreaterThan(0)
      })
    })

    it('all step types have defined expandable property', () => {
      Object.entries(stepMetadata).forEach(([, metadata]) => {
        expect(typeof metadata.expandable).toBe('boolean')
      })
    })

    it('trigger nodes disable target handle', () => {
      expect(stepMetadata.trigger.disableTarget).toBe(true)
      expect(stepMetadata.scheduledTrigger.disableTarget).toBe(true)
    })

    it('only loop node enables end handle', () => {
      const nodesWithEnableEnd = Object.entries(stepMetadata).filter(([, metadata]) => metadata.enableEnd === true)
      expect(nodesWithEnableEnd).toHaveLength(1)
      expect(nodesWithEnableEnd[0][0]).toBe('loop')
    })
  })

  describe('metadata interface compliance', () => {
    it('all entries conform to StepMetadata interface', () => {
      Object.entries(stepMetadata).forEach(([, metadata]) => {
        const typedMetadata: StepMetadata = metadata
        expect(typedMetadata.label).toBeDefined()

        // Optional fields should be correct types if present
        if (typedMetadata.icon !== undefined) {
          expect(typeof typedMetadata.icon).toBe('function')
        }
        if (typedMetadata.className !== undefined) {
          expect(typeof typedMetadata.className).toBe('string')
        }
        if (typedMetadata.disableTarget !== undefined) {
          expect(typeof typedMetadata.disableTarget).toBe('boolean')
        }
        if (typedMetadata.enableEnd !== undefined) {
          expect(typeof typedMetadata.enableEnd).toBe('boolean')
        }
        if (typedMetadata.enableStart !== undefined) {
          expect(typeof typedMetadata.enableStart).toBe('boolean')
        }
        if (typedMetadata.expandable !== undefined) {
          expect(typeof typedMetadata.expandable).toBe('boolean')
        }
      })
    })
  })
})

describe('executorMetadata', () => {
  describe('executor types', () => {
    it('has metadata for script executor', () => {
      expect(executorMetadata.script).toBeDefined()
      expect(executorMetadata.script.label).toBe('Script')
      expect(executorMetadata.script.icon).toBeDefined()
    })

    it('has metadata for agentic executor', () => {
      expect(executorMetadata.agentic).toBeDefined()
      expect(executorMetadata.agentic.label).toBe('Task Agent')
      expect(executorMetadata.agentic.icon).toBeDefined()
    })

    it('has metadata for http_request executor', () => {
      expect(executorMetadata.http_request).toBeDefined()
      expect(executorMetadata.http_request.label).toBe('REST API')
      expect(executorMetadata.http_request.icon).toBeDefined()
    })

    it('has metadata for aap_job_template executor', () => {
      expect(executorMetadata.aap_job_template).toBeDefined()
      expect(executorMetadata.aap_job_template.label).toBe('AAP Job')
      expect(executorMetadata.aap_job_template.icon).toBeDefined()
    })

    it('has metadata for internal aap key matching aap_job_template', () => {
      expect(executorMetadata.aap).toBe(executorMetadata.aap_job_template)
      expect(executorMetadata.aap.label).toBe('AAP Job')
    })

    it('has metadata for approval executor', () => {
      expect(executorMetadata.approval).toBeDefined()
      expect(executorMetadata.approval.label).toBe('Approval')
      expect(executorMetadata.approval.icon).toBeDefined()
    })
  })

  describe('executor metadata structure', () => {
    it('all executors have label and icon', () => {
      Object.entries(executorMetadata).forEach(([, metadata]) => {
        expect(metadata.label).toBeDefined()
        expect(typeof metadata.label).toBe('string')
        expect(metadata.icon).toBeDefined()
        // Icon can be a function (React component), object (SVG import), or string
        expect(['function', 'object', 'string']).toContain(typeof metadata.icon)
      })
    })
  })
})
