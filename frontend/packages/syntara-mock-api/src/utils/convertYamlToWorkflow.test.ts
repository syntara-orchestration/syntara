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

    expect(workflow.version.created_by).toEqual({
      id: expect.any(String),
      name: 'system',
      type: 'user',
    })
  })

  it('seeds the workflow and its version with the same creator', () => {
    const workflow = convertYamlToWorkflow(yamlPath, 'wf-red-green', 'system', baseDir)

    expect(workflow.version.created_by).toEqual(workflow.created_by)
  })
})
