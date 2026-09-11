import { ClipboardCopy, Flex, FlexItem, FormGroup, StackItem } from '@patternfly/react-core'
import type { ReactNode } from 'react'

import { SynLabel } from '../../../components/labels/SynLabel'

type WebhookUrlPreviewProps = {
  /** Full webhook URL to display in the ClipboardCopy field. */
  url: string
  /** Label element for the URL field. */
  urlLabel: ReactNode
  /** HTTP method badge text (defaults to "POST"). */
  methodLabel?: string
  /** DOM id prefix for the FormGroup and input elements (defaults to "webhook"). */
  fieldIdPrefix?: string
}

/**
 * Compact HTTP method badge + URL preview (ClipboardCopy),
 * used by both webhook and EDA trigger forms.
 */
export function WebhookUrlPreview({
  url,
  urlLabel,
  methodLabel = 'POST',
  fieldIdPrefix = 'webhook',
}: Readonly<WebhookUrlPreviewProps>) {
  return (
    <StackItem>
      <FormGroup label={urlLabel} fieldId={`${fieldIdPrefix}-url`}>
        <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
          <FlexItem>
            <SynLabel color="blue">{methodLabel}</SynLabel>
          </FlexItem>
          <FlexItem grow={{ default: 'grow' }}>
            <ClipboardCopy isReadOnly aria-label="Webhook URL">
              {url}
            </ClipboardCopy>
          </FlexItem>
        </Flex>
      </FormGroup>
    </StackItem>
  )
}
