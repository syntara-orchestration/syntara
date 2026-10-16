import { ExpandableSection, StackItem } from '@patternfly/react-core'
import { useMemo, useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { SynCodeBlock } from '../../../components/details/SynCodeBlock'

import { generateSampleBody } from './simpleSchemaUtils'
import type { TriggerFormData } from './triggerFormSchema'

type SampleCurlSectionProps = {
  url: string
}

function buildCurlCommand(url: string, body: string): string {
  const escapedUrl = url.replaceAll("'", String.raw`'\''`)
  const escapedBody = body.replaceAll("'", String.raw`'\''`)
  return String.raw`curl -X POST '${escapedUrl}' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -d '${escapedBody}'`
}

export function SampleCurlSection({ url }: Readonly<SampleCurlSectionProps>) {
  const { control } = useFormContext<TriggerFormData>()
  const inputSchema = useWatch({ control, name: 'inputSchema' })
  const [expanded, setExpanded] = useState(false)

  const sampleBody = useMemo(() => generateSampleBody(inputSchema), [inputSchema])
  const curlCommand = useMemo(() => buildCurlCommand(url, sampleBody), [url, sampleBody])

  return (
    <StackItem>
      <ExpandableSection toggleText="Sample request" isExpanded={expanded} onToggle={(_event, val) => setExpanded(val)}>
        <SynCodeBlock enableCopy noMaxHeight>
          {curlCommand}
        </SynCodeBlock>
      </ExpandableSection>
    </StackItem>
  )
}
