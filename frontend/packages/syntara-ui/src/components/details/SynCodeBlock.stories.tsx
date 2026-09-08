import type { Meta, StoryObj } from '@storybook/react-vite'

import { SynCodeBlock } from './SynCodeBlock'

const SCRIPT = `#!/bin/bash
set -euo pipefail

echo "Deploying my-app to production..."
kubectl apply -f k8s/deployment.yaml
kubectl rollout status deployment/my-app --timeout=120s
echo "Rollout complete."`

const EVENT_PAYLOAD = {
  event: 'job.completed',
  job_id: 'j-8f3a2c1d',
  workflow_id: 'wf-deploy-prod',
  timestamp: '2024-11-15T14:32:01Z',
  result: {
    status: 'success',
    duration_ms: 4821,
    outputs: { artifact_url: 's3://builds/my-app/v2.3.1.tar.gz' },
  },
}

const LOG_LINES = [
  'Waiting for lock...',
  'Connecting to target host',
  'Running preflight checks',
  'Applying configuration',
  'Step completed successfully',
]

const LARGE_LOG = Array.from(
  { length: 50 },
  (_, i) =>
    `[2024-11-15 14:32:${String(i).padStart(2, '0')}] INFO  step-${String(i + 1).padStart(2, '0')}: ${LOG_LINES[i % LOG_LINES.length]}`
).join('\n')

const meta: Meta<typeof SynCodeBlock> = {
  component: SynCodeBlock,
}
export default meta

type Story = StoryObj<typeof meta>

/** Script content shown in a builder step, execution result, or policy view. */
export const Default: Story = {
  args: {
    children: SCRIPT,
  },
}

/** `jsonObject` is automatically pretty-printed with 2-space indentation. */
export const JSONPayload: Story = {
  args: {
    jsonObject: EVENT_PAYLOAD,
  },
}

/** `enableCopy` adds a copy-to-clipboard button — useful for scripts and API tokens. */
export const WithCopyButton: Story = {
  args: {
    children: SCRIPT,
    enableCopy: true,
  },
}

/** `enableExpand` opens the content in a modal — useful when the inline block is too small to read comfortably. */
export const WithExpandButton: Story = {
  args: {
    jsonObject: EVENT_PAYLOAD,
    enableExpand: true,
    expandTitle: 'Job result',
  },
}

/** Copy and expand together — the typical setup for execution output panels. */
export const CopyAndExpand: Story = {
  args: {
    jsonObject: EVENT_PAYLOAD,
    enableCopy: true,
    enableExpand: true,
    expandTitle: 'Job result',
  },
}

/**
 * Large content is capped at 24 rem and scrolls by default.
 * Pass `noMaxHeight` only when the parent container already constrains height (e.g. a sidebar or drawer).
 */
export const LargeOutput: Story = {
  args: {
    children: LARGE_LOG,
  },
}
