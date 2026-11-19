import { Button, Content, ContentVariants, Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { useMemo, useState } from 'react'

import { ShikiServiceLoaderContext } from './shiki-service-context'
import type { ShikiServiceLoader } from './shiki-service-context'
import { loadShikiService as loadRealShikiService } from './shiki-service-loader'
import { SynCodeBlock } from './SynCodeBlock'

const SCRIPT = `#!/bin/bash
set -euo pipefail

echo "Deploying my-app to production..."
kubectl apply -f k8s/deployment.yaml
kubectl rollout status deployment/my-app --timeout=120s
echo "Rollout complete."`

const HIGHLIGHTED_JSON = `{
  "workflow": "nightly-deploy",
  "attempt": 3,
  "enabled": true,
  "metadata": {
    "owner": "platform-team",
    "regions": ["us-east-1", "eu-west-1"]
  },
  "steps": [
    { "name": "build", "complete": true },
    { "name": "deploy", "complete": false }
  ]
}`

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

type DeferredLoad = Readonly<{
  promise: Promise<void>
  resolve: () => void
  reject: () => void
}>

type DemoPhase = 'pending' | 'released' | 'ready' | 'failed'

type DemoState = Readonly<{
  attempt: Readonly<{ id: number; load: DeferredLoad }>
  phase: DemoPhase
}>

function createDeferredLoad(): DeferredLoad {
  let settle: (error?: Error) => void = () => undefined
  const promise = new Promise<void>((resolve, reject) => {
    settle = (error) => {
      if (error) reject(error)
      else resolve()
    }
  })

  return {
    promise,
    resolve: () => settle(),
    reject: () => settle(new Error('Shiki load rejected in the Storybook demo')),
  }
}

function createDemoState(id: number): DemoState {
  return { attempt: { id, load: createDeferredLoad() }, phase: 'pending' }
}

function ShikiLoadingStatesDemo() {
  const [demo, setDemo] = useState(() => createDemoState(0))
  const loader = useMemo<ShikiServiceLoader>(
    () => ({
      getLoadedShikiService: () => undefined,
      loadShikiService: async () => {
        await demo.attempt.load.promise
        const service = await loadRealShikiService()
        return {
          ...service,
          highlightCode: async (source, language) => {
            const tokens = await service.highlightCode(source, language)
            setDemo((current) => (current.attempt === demo.attempt ? { ...current, phase: 'ready' } : current))
            return tokens
          },
        }
      },
    }),
    [demo.attempt]
  )

  const resetDemo = () => {
    setDemo((current) => createDemoState(current.attempt.id + 1))
  }
  const resolveLoad = () => {
    setDemo((current) => ({ ...current, phase: 'released' }))
    demo.attempt.load.resolve()
  }
  const rejectLoad = () => {
    setDemo((current) => ({ ...current, phase: 'failed' }))
    demo.attempt.load.reject()
  }

  const statusText = {
    pending:
      'Pending: the Storybook harness is holding the real Shiki loader. SynCodeBlock keeps the source readable until you resolve or reject the load.',
    released: 'The load was released. Shiki is initializing; the source remains readable until highlighting is ready.',
    ready: 'Highlighting is complete and the colored code is visible.',
    failed: 'The load was rejected. SynCodeBlock keeps the source readable as its fallback.',
  } satisfies Record<DemoPhase, string>

  return (
    <ShikiServiceLoaderContext value={loader}>
      <Stack hasGutter>
        <StackItem>
          <Content component={ContentVariants.p} role="status" aria-live="polite">
            {statusText[demo.phase]}
          </Content>
        </StackItem>
        <StackItem>
          <Flex gap={{ default: 'gapSm' }} flexWrap={{ default: 'wrap' }}>
            <FlexItem>
              <Button type="button" variant="primary" onClick={resolveLoad} isDisabled={demo.phase !== 'pending'}>
                Resolve Shiki load
              </Button>
            </FlexItem>
            <FlexItem>
              <Button type="button" variant="secondary" onClick={rejectLoad} isDisabled={demo.phase !== 'pending'}>
                Reject Shiki load
              </Button>
            </FlexItem>
            <FlexItem>
              <Button type="button" variant="secondary" onClick={resetDemo}>
                Reset demo
              </Button>
            </FlexItem>
          </Flex>
        </StackItem>
        <StackItem>
          <SynCodeBlock language="json" highlightKey={`storybook-load-${demo.attempt.id}`}>
            {HIGHLIGHTED_JSON}
          </SynCodeBlock>
        </StackItem>
      </Stack>
    </ShikiServiceLoaderContext>
  )
}

const meta: Meta<typeof SynCodeBlock> = {
  component: SynCodeBlock,
  parameters: {
    docs: {
      description: {
        component:
          'Code strings can opt into Shiki syntax highlighting with a language. The GitHub High Contrast light/dark pair follows the Storybook Color Scheme toolbar. Source stays readable as plain text while Shiki loads and if highlighting fails; there is no loading placeholder.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** A real SynCodeBlock highlighted by Shiki with the app's GitHub High Contrast theme pair. */
export const Default: Story = {
  args: {
    children: HIGHLIGHTED_JSON,
    language: 'json',
  },
  parameters: {
    docs: {
      description: {
        story:
          'Use the Color Scheme toolbar in the Storybook header to compare the GitHub High Contrast light and dark variants. Nested objects and arrays make bracket-pair colors easy to inspect.',
      },
    },
  },
}

/** Bash grammar is loaded on demand; the original source remains visible during that request. */
export const BashHighlighting: Story = {
  args: {
    children: SCRIPT,
    language: 'bash',
  },
}

/** Stable plain-text rendering, matching the visible fallback while highlighting is pending or unavailable. */
export const PlainSourceFallback: Story = {
  args: {
    children: HIGHLIGHTED_JSON,
  },
  parameters: {
    docs: {
      description: {
        story:
          'This story omits `language` so the plain-text view is deterministic. SynCodeBlock keeps this same source visible while an async highlight is pending or after a failure; deferred pending, ready, and failure behavior is covered by the component tests.',
      },
    },
  },
}

/** Hold, resolve, or reject the real Shiki loader to inspect pending, ready, and fallback output. */
export const AsyncHighlightStates: Story = {
  render: () => <ShikiLoadingStatesDemo />,
  parameters: {
    controls: { disable: true },
    docs: {
      description: {
        story:
          'This Storybook-only harness holds the real Shiki loader so pending is persistent and repeatable. Resolve Shiki load to see actual highlighting, reject it to inspect the plain-source fallback, and reset to start again. The state message belongs to the harness; SynCodeBlock itself keeps source visible without a loading placeholder.',
      },
    },
  },
}

/** `jsonObject` is automatically pretty-printed with 2-space indentation. */
export const JSONPayload: Story = {
  args: {
    jsonObject: EVENT_PAYLOAD,
    language: 'json',
  },
}

/** `enableCopy` adds a copy-to-clipboard button — useful for scripts and API tokens. */
export const WithCopyButton: Story = {
  args: {
    children: SCRIPT,
    language: 'bash',
    enableCopy: true,
  },
}

/** `enableExpand` opens the content in a modal — useful when the inline block is too small to read comfortably. */
export const WithExpandButton: Story = {
  args: {
    jsonObject: EVENT_PAYLOAD,
    language: 'json',
    enableExpand: true,
    expandTitle: 'Job result',
  },
}

/** Copy and expand together — the typical setup for execution output panels. */
export const CopyAndExpand: Story = {
  args: {
    jsonObject: EVENT_PAYLOAD,
    language: 'json',
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
