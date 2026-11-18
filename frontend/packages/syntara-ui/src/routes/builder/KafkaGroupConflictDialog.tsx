import { Content } from '@patternfly/react-core'
import { useId } from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'

import type { KafkaGroupConflict } from './node-forms/kafkaPublishedGroups'

type Props = Readonly<{
  conflicts?: KafkaGroupConflict[]
  isPending: boolean
  onConfirm: () => void
  onCancel: () => void
}>

export function KafkaGroupConflictDialog({ conflicts, isPending, onConfirm, onCancel }: Props) {
  const labelId = useId()
  const descriptionId = useId()
  return (
    <SynConfirmationDialog
      isOpen={Boolean(conflicts?.length)}
      aria-labelledby={labelId}
      aria-describedby={descriptionId}
      title="Use the published consumer groups?"
      confirmLabel="Use published groups and publish"
      confirmLoading={isPending}
      onConfirm={onConfirm}
      onClose={onCancel}
    >
      <Content component="p">
        These Kafka sources already have fixed consumer groups. Publishing this draft requires carrying forward those
        established IDs. Cancel to keep the draft unchanged.
      </Content>
      <Content component="ul">
        {conflicts?.map(({ triggerId, draftGroup, source }) => (
          <Content component="li" key={triggerId}>
            {triggerId}: replace <code>{draftGroup}</code> with <code>{source.group_id}</code> for {source.topic}.
          </Content>
        ))}
      </Content>
    </SynConfirmationDialog>
  )
}
