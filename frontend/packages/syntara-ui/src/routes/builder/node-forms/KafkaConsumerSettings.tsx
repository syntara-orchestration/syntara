import { Button, Content, ContentVariants, Stack, StackItem, TextInput, Title } from '@patternfly/react-core'
import { KafkaOffsetGapPolicyEnum, KafkaStartPositionEnum } from '@syntara/contracts'
import { useFormContext, useWatch } from 'react-hook-form'

import { FieldHelpPopover } from '../../../components/FieldHelpPopover'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynSelectField } from '../../../components/forms/SynSelectField'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { detachPromise } from '../../../utils/detachPromise'

import type { TriggerFormData } from './triggerFormSchema'
import { useKafkaPublishedSource } from './useKafkaPublishedSource'

const positionOptions = [
  { value: KafkaStartPositionEnum.LATEST, label: 'Latest' },
  { value: KafkaStartPositionEnum.EARLIEST, label: 'Earliest' },
]
const addedPartitionOptions = [positionOptions[1], positionOptions[0]]
const gapOptions = [
  { value: KafkaOffsetGapPolicyEnum.FAIL, label: 'Fail' },
  { value: KafkaOffsetGapPolicyEnum.EARLIEST, label: 'Earliest' },
  { value: KafkaOffsetGapPolicyEnum.LATEST, label: 'Latest' },
]
const startHelp =
  'Latest starts with new messages at the visible-end boundary saved when each initial partition initializes. Earliest starts at its earliest retained message. Valid committed offsets and previously saved boundaries take precedence. Changing this setting does not replay messages.'
const partitionHelp =
  'Applies to partitions outside the saved first-activation set, even if discovered during initialization. Earliest includes retained messages produced before discovery; Latest starts at the saved visible end. Saved decisions take precedence.'
const gapHelp =
  'When an established checkpoint is missing or invalid, Earliest resumes at the earliest retained message. Latest resumes at the visible end and can skip retained messages. Fail holds only the affected partition; healthy partitions continue. Previously saved recovery decisions take precedence.'
const groupHelp =
  'Use a group exclusively for this Syntara source. Custom IDs accept 1–512 ASCII letters, numbers, dots, underscores, or hyphens. The group is fixed after the first successful publication, including while unpublished. Changing the Integration or topic creates a replacement source.'

export function KafkaConsumerSettings({
  workflowId,
  triggerId,
  isReadOnly,
}: Readonly<{
  workflowId?: string | null
  triggerId?: string
  isReadOnly: boolean
}>) {
  const { control } = useFormContext<TriggerFormData>()
  const [integrationId, topic] = useWatch({ control, name: ['integrationId', 'topic'] })
  const publication = useKafkaPublishedSource(isReadOnly ? undefined : workflowId, triggerId)
  const isPublishedSource = Boolean(
    publication.source && publication.source.integration_id === integrationId && publication.source.topic === topic
  )
  const isGroupLocked = isReadOnly || publication.isChecking || publication.isError || isPublishedSource
  const groupHint = isPublishedSource
    ? 'This source’s consumer group is fixed after its first successful publication. The published group is preserved.'
    : 'Leave blank for an auto-generated ID for a new source. The group becomes fixed after the first successful publication.'

  return (
    <section aria-labelledby="kafka-consumer-settings-heading">
      <Stack hasGutter>
        <StackItem>
          <Title headingLevel="h3" id="kafka-consumer-settings-heading">
            Consumer settings
          </Title>
        </StackItem>
        <StackItem>
          <SynSelectField<TriggerFormData, 'kafkaStart.position'>
            name="kafkaStart.position"
            label="Start position"
            fieldId="kafka-start-position"
            options={positionOptions}
            placeholder="Latest"
            fallbackValue={KafkaStartPositionEnum.LATEST}
            isDisabled={isReadOnly}
            hint="Applies when an initial partition needs a new starting position. Saved progress takes precedence."
            labelHelp={<FieldHelpPopover headerContent="Start position" helpText={startHelp} />}
          />
        </StackItem>
        <StackItem>
          <SynSelectField<TriggerFormData, 'kafkaStart.added_partition_position'>
            name="kafkaStart.added_partition_position"
            label="New partition position"
            fieldId="kafka-added-partition-position"
            options={addedPartitionOptions}
            placeholder="Earliest"
            fallbackValue={KafkaStartPositionEnum.EARLIEST}
            isDisabled={isReadOnly}
            hint="Applies when a partition outside the initial set is discovered."
            labelHelp={<FieldHelpPopover headerContent="New partition position" helpText={partitionHelp} />}
          />
        </StackItem>
        <StackItem>
          <SynSelectField<TriggerFormData, 'kafkaStart.offset_gap_policy'>
            name="kafkaStart.offset_gap_policy"
            label="Offset gap policy"
            fieldId="kafka-offset-gap-policy"
            options={gapOptions}
            placeholder="Earliest"
            fallbackValue={KafkaOffsetGapPolicyEnum.EARLIEST}
            isDisabled={isReadOnly}
            hint="Applies when an established checkpoint is missing or invalid. Latest can skip retained messages."
            labelHelp={<FieldHelpPopover headerContent="Offset gap policy" helpText={gapHelp} />}
          />
        </StackItem>
        <StackItem>
          <SynFormField<TriggerFormData, 'kafkaGroupId'>
            name="kafkaGroupId"
            label="Consumer group ID"
            fieldId="kafka-group-id"
            hint={groupHint}
            labelHelp={<FieldHelpPopover headerContent="Consumer group ID" helpText={groupHelp} />}
          >
            {({ field, fieldState, describedBy }) => (
              <TextInput
                id="kafka-group-id"
                name={field.name}
                ref={field.ref}
                value={isPublishedSource ? (publication.source?.group_id ?? '') : (field.value ?? '')}
                placeholder={isPublishedSource ? 'Published group' : 'Auto-generated'}
                isDisabled={isGroupLocked}
                aria-describedby={describedBy}
                aria-invalid={Boolean(fieldState.error)}
                validated={fieldState.error ? 'error' : 'default'}
                onBlur={field.onBlur}
                onChange={(_event, value) => field.onChange(value)}
              />
            )}
          </SynFormField>
        </StackItem>
        {publication.isChecking && (
          <StackItem>
            <Content component={ContentVariants.p}>Checking published consumer groups…</Content>
          </StackItem>
        )}
        {publication.isError && (
          <StackItem>
            <SynErrorState title="Unable to check published consumer groups" message={publication.error} />
            <Button variant="secondary" onClick={() => detachPromise(publication.refetch())}>
              Retry published consumer groups
            </Button>
          </StackItem>
        )}
        <StackItem>
          <Content component={ContentVariants.p}>
            Changes apply on the next publish. Valid checkpoints and saved position decisions are preserved.
          </Content>
        </StackItem>
      </Stack>
    </section>
  )
}
