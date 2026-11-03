import type { TaskActivity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { DetectedExecutorType, detectTaskNodeType, type TaskActivityWithMetadata } from './detectTaskNodeType'

describe('detectTaskNodeType', () => {
  const createBaseTask = (overrides: Partial<TaskActivity> = {}): TaskActivity =>
    ({
      type: 'script',
      id: 'test-task-1',
      name: 'Test Task',
      parameters: {
        language: 'python',
        code: 'print("hello")',
      },
      ...overrides,
    }) as TaskActivity

  describe('basic detection', () => {
    it('returns the type for a basic script task', () => {
      const task = createBaseTask()
      const result = detectTaskNodeType(task)

      expect(result).toEqual({
        detectedExecutorType: 'script',
        connectorData: null,
        actualExecutor: 'script',
      })
    })

    it('returns agentic type for agentic tasks', () => {
      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: 'Do something',
          model: 'claude-3-sonnet',
        },
      })
      const result = detectTaskNodeType(task)

      expect(result.detectedExecutorType).toBe('agentic')
      expect(result.actualExecutor).toBe('agentic')
    })

    it('returns http_request type for HTTP request tasks', () => {
      const task = createBaseTask({
        type: 'http_request',
        parameters: { method: 'GET', url: 'https://api.example.com' },
      })
      const result = detectTaskNodeType(task)

      expect(result.detectedExecutorType).toBe('http_request')
      expect(result.actualExecutor).toBe('http_request')
    })

    it('returns aap_job_template type for AAP tasks', () => {
      const task = createBaseTask({
        type: 'aap_job_template',
        parameters: { job_template_id: 123 },
      })
      const result = detectTaskNodeType(task)

      expect(result.detectedExecutorType).toBe('aap_job_template')
      expect(result.actualExecutor).toBe('aap_job_template')
    })
  })

  describe('metadata override detection', () => {
    it('rejects invalid __executorType from metadata for security', () => {
      const task = createBaseTask() as TaskActivityWithMetadata
      task.metadata = { __executorType: 'custom-executor' }

      const result = detectTaskNodeType(task)

      // SECURITY: Invalid executor types are rejected, falls back to task.type
      expect(result).toEqual({
        detectedExecutorType: 'script',
        connectorData: null,
        actualExecutor: 'script',
      })
    })

    it('accepts valid API __executorType from metadata', () => {
      const task = createBaseTask({
        type: 'agentic',
        parameters: { prompt: 'test' },
      }) as TaskActivityWithMetadata
      task.metadata = { __executorType: 'aap_job_template' }

      const result = detectTaskNodeType(task)

      expect(result.detectedExecutorType).toBe('aap_job_template')
      expect(result.actualExecutor).toBe('aap_job_template')
    })

    it('SECURITY: rejects internal-only aap type from metadata override', () => {
      const task = createBaseTask({
        type: 'agentic',
        parameters: { prompt: 'test' },
      }) as TaskActivityWithMetadata
      task.metadata = { __executorType: 'aap' }

      const result = detectTaskNodeType(task)

      // 'aap' is internal-only — metadata override is rejected, falls back to task.type
      expect(result.detectedExecutorType).toBe('agentic')
      expect(result.actualExecutor).toBe('agentic')
    })

    it('accepts all valid executor types from ExecutorTypeEnum', () => {
      const validTypes = ['script', 'http_request', 'agentic', 'aap_job_template', 'approval'] as const

      for (const executorType of validTypes) {
        const task = createBaseTask() as TaskActivityWithMetadata
        task.metadata = { __executorType: executorType }

        const result = detectTaskNodeType(task)

        expect(result.detectedExecutorType).toBe(executorType)
        expect(result.actualExecutor).toBe(executorType)
      }
    })
  })

  describe('AAP connector detection in agentic nodes', () => {
    it('detects AAP connector from JSON prompt and sets detectedExecutorType', () => {
      const promptPayload = {
        __type: 'connector',
        connectorId: 'ansible-automation-platform',
        operation: 'run_job_template',
        parameters: { template_id: 123 },
      }

      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: JSON.stringify(promptPayload),
          model: 'claude-3-sonnet',
        },
      })

      const result = detectTaskNodeType(task)

      // CRITICAL: Both detectedExecutorType and actualExecutor should be 'aap'
      expect(result.detectedExecutorType).toBe(DetectedExecutorType.AAP)
      expect(result.actualExecutor).toBe(DetectedExecutorType.AAP)
      expect(result.connectorData).toBeNull()
    })

    it('does not detect AAP when prompt is plain text', () => {
      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: 'Run a job template on AAP',
          model: 'claude-3-sonnet',
        },
      })

      const result = detectTaskNodeType(task)

      expect(result.detectedExecutorType).toBe('agentic')
      expect(result.actualExecutor).toBe('agentic')
    })

    it('does not detect AAP when connectorId is different', () => {
      const promptPayload = {
        __type: 'connector',
        connectorId: 'some-other-connector',
        operation: 'do_something',
      }

      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: JSON.stringify(promptPayload),
          model: 'claude-3-sonnet',
        },
      })

      const result = detectTaskNodeType(task)

      expect(result.detectedExecutorType).toBe('agentic')
      expect(result.actualExecutor).toBe('agentic')
    })

    it('does not detect AAP when __type is not "connector"', () => {
      const promptPayload = {
        __type: 'something-else',
        connectorId: 'ansible-automation-platform',
      }

      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: JSON.stringify(promptPayload),
          model: 'claude-3-sonnet',
        },
      })

      const result = detectTaskNodeType(task)

      expect(result.detectedExecutorType).toBe('agentic')
      expect(result.actualExecutor).toBe('agentic')
    })

    it('handles invalid JSON in prompt gracefully', () => {
      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: '{ invalid json',
          model: 'claude-3-sonnet',
        },
      })

      const result = detectTaskNodeType(task)

      expect(result.detectedExecutorType).toBe('agentic')
      expect(result.actualExecutor).toBe('agentic')
    })

    it('safely handles __proto__ in parsed prompt to prevent prototype pollution', () => {
      const maliciousPayload = {
        __type: 'connector',
        connectorId: 'ansible-automation-platform',
        __proto__: { polluted: true },
      }

      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: JSON.stringify(maliciousPayload),
          model: 'claude-3-sonnet',
        },
      })

      const result = detectTaskNodeType(task)

      // SECURITY: Should detect AAP connector despite __proto__ presence
      // The implementation only accesses expected properties directly
      expect(result.detectedExecutorType).toBe(DetectedExecutorType.AAP)
      expect(result.actualExecutor).toBe(DetectedExecutorType.AAP)
    })

    it('safely handles constructor in parsed prompt', () => {
      const maliciousPayload = {
        __type: 'connector',
        connectorId: 'ansible-automation-platform',
        constructor: { prototype: { polluted: true } },
      }

      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: JSON.stringify(maliciousPayload),
          model: 'claude-3-sonnet',
        },
      })

      const result = detectTaskNodeType(task)

      // SECURITY: Should detect AAP connector despite constructor presence
      expect(result.detectedExecutorType).toBe(DetectedExecutorType.AAP)
      expect(result.actualExecutor).toBe(DetectedExecutorType.AAP)
    })

    it('rejects non-object parsed values', () => {
      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: '"just a string"',
          model: 'claude-3-sonnet',
        },
      })

      const result = detectTaskNodeType(task)

      // SECURITY: Parsed value is not an object, should not detect AAP
      expect(result.detectedExecutorType).toBe('agentic')
      expect(result.actualExecutor).toBe('agentic')
    })

    it('rejects null parsed values', () => {
      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: 'null',
          model: 'claude-3-sonnet',
        },
      })

      const result = detectTaskNodeType(task)

      // SECURITY: Parsed value is null, should not detect AAP
      expect(result.detectedExecutorType).toBe('agentic')
      expect(result.actualExecutor).toBe('agentic')
    })

    it('valid metadata override takes precedence over AAP connector detection', () => {
      const promptPayload = {
        __type: 'connector',
        connectorId: 'ansible-automation-platform',
        operation: 'run_job_template',
      }

      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: JSON.stringify(promptPayload),
          model: 'claude-3-sonnet',
        },
      }) as TaskActivityWithMetadata

      task.metadata = { __executorType: 'script' }

      const result = detectTaskNodeType(task)

      // Valid override should win over AAP detection
      expect(result.detectedExecutorType).toBe('script')
      expect(result.actualExecutor).toBe('script')
    })

    it('invalid metadata override is rejected and AAP connector is detected', () => {
      const promptPayload = {
        __type: 'connector',
        connectorId: 'ansible-automation-platform',
        operation: 'run_job_template',
      }

      const task = createBaseTask({
        type: 'agentic',
        parameters: {
          prompt: JSON.stringify(promptPayload),
          model: 'claude-3-sonnet',
        },
      }) as TaskActivityWithMetadata

      task.metadata = { __executorType: 'invalid-type' }

      const result = detectTaskNodeType(task)

      // Invalid override is rejected, AAP detection should proceed
      expect(result.detectedExecutorType).toBe(DetectedExecutorType.AAP)
      expect(result.actualExecutor).toBe(DetectedExecutorType.AAP)
    })
  })

  describe('edge cases', () => {
    it('returns empty string for missing type', () => {
      const task = { id: 'test', name: 'Test', parameters: {} } as TaskActivity
      const result = detectTaskNodeType(task)

      expect(result.actualExecutor).toBe('')
      expect(result.connectorData).toBeNull()
    })

    it('connectorData is always null in v2', () => {
      const task = createBaseTask()
      const result = detectTaskNodeType(task)

      expect(result.connectorData).toBeNull()
    })
  })
})
