import { Flex, FlexItem, Label, Stack, Title } from '@patternfly/react-core'
import { useState } from 'react'

import { SynPanel } from '../../../components/layout/SynPanel'

import { InlineMockEditor } from './InlineMockEditor'
import styles from './panels.module.css'
import { parseJsonObject } from './utils/mockDataUtils'

type MockDataEditorProps = {
  predecessorName: string
  initialJson: string
  onPin: (parsed: Record<string, unknown>) => void
  onCancel: () => void
}

export function MockDataEditor({ predecessorName, initialJson, onPin, onCancel }: Readonly<MockDataEditorProps>) {
  const [mockJsonText, setMockJsonText] = useState(initialJson)
  const [jsonError, setJsonError] = useState<string | null>(null)

  function handlePinData() {
    const result = parseJsonObject(mockJsonText)
    if (!result.success) {
      setJsonError(result.error)
      return
    }
    setJsonError(null)
    onPin(result.data)
  }

  return (
    <SynPanel
      variant="raised"
      isFullHeight
      className={styles.panelContainer}
      panelMainProps={{ className: styles.panelMain }}
      panelMainBodyProps={{ className: styles.panelBodyFlex }}
    >
      <Stack hasGutter>
        <Flex direction={{ default: 'column' }} spaceItems={{ default: 'spaceItemsSm' }}>
          <FlexItem>
            <Title headingLevel="h2" size="md">
              Input
            </Title>
          </FlexItem>
          <FlexItem>
            <Label color="grey" isCompact>
              Editing mock data for: {predecessorName}
            </Label>
          </FlexItem>
        </Flex>
        <InlineMockEditor
          code={mockJsonText}
          onCodeChange={setMockJsonText}
          onPin={handlePinData}
          onCancel={onCancel}
          jsonError={jsonError}
        />
      </Stack>
    </SynPanel>
  )
}
