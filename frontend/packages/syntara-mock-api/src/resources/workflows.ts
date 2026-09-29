import type { WorkflowWithVersion } from '@syntara/contracts'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { convertYamlToWorkflow } from '../utils/convertYamlToWorkflow'

// Get the directory of this module
const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const examplesDir = join(__dirname, '../examples')

// Import all YAML workflow files
const yamlFiles = [
  'basic/conditional-demo.yaml',
  'basic/hello-world.yaml',
  'basic/loop-demo.yaml',
  'basic/parallel-demo.yaml',
  'basic/retry-demo.yaml',
  'condition/basic-condition-then-else.yaml',
  'condition/condition-no-else-branch.yaml',
  'condition/condition-with-multiple-branches.yaml',
  'conditionals/nested-conditions.yaml',
  'conditionals/positive-negative-zero.yaml',
  'edge_cases/condition_comparisons.yaml',
  'edge_cases/expression_resolution.yaml',
  'edge_cases/output_mapping_json.yaml',
  'edge_cases/retry_policy.yaml',
  'edge_cases/script_failure.yaml',
  'error-handling/error-propagation.yaml',
  'error-handling/failing-task.yaml',
  'error-handling/transient-errors.yaml',
  'join/join-aggregate-outputs.yaml',
  'join/join-all-strategy.yaml',
  'join/join-any-strategy.yaml',
  'join/join-count-strategy.yaml',
  'join/join-majority-strategy.yaml',
  'join/join-missing-branch.yaml',
  'join/join-nested-parallel.yaml',
  'join/join-sequential.yaml',
  'join/join-timeout-continue.yaml',
  'join/join-timeout-fail.yaml',
  'join/join-with-post-join-activities.yaml',
  'loops/count-loop-basic.yaml',
  'loops/count-loop-with-index.yaml',
  'loops/foreach-items.yaml',
  'loops/while-loop-basic.yaml',
  'loops/while-loop-with-max-iterations.yaml',
  'metadata/workflow-with-all-metadata.yaml',
  'metadata/workflow-with-tags.yaml',
  'metadata/workflow-with-timeout.yaml',
  'parallel/parallel-tasks.yaml',
  'parameters/activity-chaining.yaml',
  'parameters/input-expressions.yaml',
  'retry/linear-backoff-retry.yaml',
  'sequence/basic-sequence.yaml',
  'sequence/nested-sequence.yaml',
  'sequence/sequence-with-data-passing.yaml',
  'timeout-retry/activity-timeout.yaml',
  'timeout-retry/retry-policy.yaml',
  'timeout-retry/timeout-with-retry.yaml',
  'agentic/simple-research.yaml',
  'agentic/task-agent-with-files.yaml',
  'api/simple-get-request.yaml',
  'api/post-with-body.yaml',
  'mixed/sequential-mixed-types.yaml',
  'converge/converge-all-strategy.yaml',
  'approval/approval-gate-basic.yaml',
  'approval/deployment-approval.yaml',
]

// Project IDs to distribute workflows across
const projectIds = ['p-001', 'p-002']

/**
 * Deterministic, non-cryptographic string hash (FNV-1a-ish) used to derive a stable
 * pseudo-index from a file path. Good enough for evenly distributing a fixed set of
 * paths across `projectIds` — we only need determinism and a roughly uniform spread,
 * not collision resistance.
 */
function stableHash(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i++) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0
  }
  return hash
}

// Convert all YAML files to WorkflowWithVersion objects.
//
// IDs and project assignment are derived from each file's own path — never from its
// position in `yamlFiles` — so that adding, removing, or reordering an unrelated entry
// (e.g. a fixture merged in from `devel` after this list was last touched) can never
// change an *existing* workflow's id or project. Tests pin specific workflows by id
// (see MOCK_HTTP_WORKFLOW_ID etc. in e2e/visual-regression/page-entries-interactive.ts);
// a positional id silently reassigns those constants to a different workflow — and a
// positional (`index % projectIds.length`) project assignment silently reshuffles which
// project a workflow belongs to — whenever the list shifts.
export const workflows: (WorkflowWithVersion & { project_id: string })[] = yamlFiles
  .map((file) => {
    const filePath = join(examplesDir, file)
    const id = file.replace(/\.yaml$/, '').replace(/\//g, '-')
    const workflow = convertYamlToWorkflow(filePath, id, 'system', examplesDir)
    const projectId = projectIds[stableHash(id) % projectIds.length]
    return { ...workflow, project_id: projectId }
  })
  .sort((a, b) => a.name.localeCompare(b.name))
