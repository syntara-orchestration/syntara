import { SearchInput, Stack, StackItem } from '@patternfly/react-core'
import { useMemo, useState } from 'react'

import { SynCodeBlock } from '../../../../components/details/SynCodeBlock'

export type OutputJsonViewProps = {
  data: Record<string, unknown> | null
}

export function OutputJsonView({ data }: Readonly<OutputJsonViewProps>) {
  const [searchTerm, setSearchTerm] = useState('')

  const fullJson = useMemo(() => (data ? JSON.stringify(data, null, 2) : ''), [data])

  const filteredContent = useMemo(() => {
    if (!fullJson || !searchTerm) return undefined
    const lines = fullJson.split('\n')
    return lines.filter((line) => line.toLowerCase().includes(searchTerm.toLowerCase())).join('\n')
  }, [fullJson, searchTerm])

  if (!data) {
    return null
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <SearchInput
          aria-label="Search json output"
          placeholder="Search json output"
          value={searchTerm}
          onChange={(_event, value) => setSearchTerm(value)}
          onClear={() => setSearchTerm('')}
        />
      </StackItem>
      <StackItem isFilled>
        <SynCodeBlock enableCopy enableExpand expandTitle="Output JSON" noMaxHeight copyContent={fullJson}>
          {filteredContent ?? fullJson}
        </SynCodeBlock>
      </StackItem>
    </Stack>
  )
}
