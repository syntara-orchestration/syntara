import { mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { convertYamlToWorkflow } from './convertYamlToWorkflow'

const MINIMAL_WORKFLOW_YAML = `---
schema_version: "2.0.0"
name: red-green-fixture
description: Minimal workflow used to assert seeded audit-field shapes
triggers:
  - id: trigger_manual
    type: manual_trigger
nodes:
  - id: noop
    name: Noop
    type: script
    parameters:
      language: bash
      script: "true"
edges: []
`

const EXPECTED_SEED_USER = {
  id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
  name: 'system',
  type: 'user',
} as const

describe('convertYamlToWorkflow audit fields', () => {
  let baseDir: string
  let yamlPath: string

  beforeAll(() => {
    baseDir = mkdtempSync(join(tmpdir(), 'mock-api-yaml-'))
    yamlPath = join(baseDir, 'fixture.yaml')
    writeFileSync(yamlPath, MINIMAL_WORKFLOW_YAML, 'utf-8')
  })

  afterAll(() => {
    rmSync(baseDir, { recursive: true, force: true })
  })

  // Regression guard: the WorkflowVersionRead contract types created_by as a
  // UserReference ({ id, name }) | null, but this converter seeded a bare
  // principal id string, so YAML-seeded versions rendered a raw UUID as the
  // author with no user link.
  it('seeds a version created_by as a UserReference, not a bare id string', () => {
    const workflow = convertYamlToWorkflow(yamlPath, 'wf-red-green', 'system', baseDir)

    expect(workflow.version.created_by).toEqual(EXPECTED_SEED_USER)
  })

  it('seeds workflow audit fields as UserReferences with the expected principal', () => {
    const workflow = convertYamlToWorkflow(yamlPath, 'wf-red-green', 'system', baseDir)

    expect(workflow.created_by).toEqual(EXPECTED_SEED_USER)
    expect(workflow.updated_by).toEqual(EXPECTED_SEED_USER)
  })

  it('preserves YAML fields and infers the missing trigger-to-entry edge', () => {
    const workflow = convertYamlToWorkflow(yamlPath, 'wf-red-green', 'system', baseDir)

    expect(workflow.version.workflow_definition).toEqual({
      schema_version: '2.0.0',
      name: 'red-green-fixture',
      description: 'Minimal workflow used to assert seeded audit-field shapes',
      triggers: [{ id: 'trigger_manual', type: 'manual_trigger' }],
      nodes: [
        {
          id: 'noop',
          name: 'Noop',
          type: 'script',
          parameters: { language: 'bash', script: 'true' },
        },
      ],
      edges: [{ from: 'trigger_manual', to: 'noop' }],
    })
  })
})
