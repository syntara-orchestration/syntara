import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
} from '@dnd-kit/core'
import { restrictToVerticalAxis } from '@dnd-kit/modifiers'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  Button,
  Flex,
  FlexItem,
  FormSection,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { RhUiCaretDownIcon, RhUiAddIcon, RhUiGripVerticalFillIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { useLayoutEffect, useRef, useState } from 'react'
import { useFieldArray, useFormContext, useWatch } from 'react-hook-form'

import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { FormFieldError } from '../../../components/FormFieldError'
import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'
import { SynSelectField } from '../../../components/forms/SynSelectField'
import { SynTextAreaField } from '../../../components/forms/SynTextAreaField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useIsVersionView } from '../VersionViewContext'

import { KafkaPublishByteFields } from './KafkaPublishByteFields'
import { KAFKA_MAX_HEADERS, type KafkaPublishFormData } from './kafkaPublishFormSchema'
import styles from './KafkaPublishMessageFields.module.css'
import { nodeHelp } from './shared/nodeFieldHelp'
import { KAFKA_PUBLISH_HEADERS_HELP } from './shared/nodeFieldHelpText'

const HEADER_SOURCES = [
  { value: 'entries', label: 'Ordered entries' },
  { value: 'template', label: 'Full-value template' },
]

function SortableHeader({
  fieldId,
  index,
  readOnly,
  onRemove,
}: Readonly<{
  fieldId: string
  index: number
  readOnly: boolean
  onRemove: () => void
}>) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: fieldId,
    disabled: readOnly,
  })
  const label = `Header ${String(index + 1)}`
  const {
    formState: { errors },
  } = useFormContext<KafkaPublishFormData>()
  const [expanded, setExpanded] = useState(true)
  const hasError = Boolean(errors.headers?.[index])
  const isExpanded = expanded || hasError
  const contentId = `header-content-${fieldId}`
  return (
    <div
      ref={setNodeRef}
      role="group"
      aria-label={label}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={isDragging ? styles.dragging : undefined}
    >
      <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsFlexStart' }}>
        <FlexItem>
          <Button
            ref={setActivatorNodeRef}
            type="button"
            variant="plain"
            className={styles.dragHandle}
            isDisabled={readOnly}
            {...(readOnly ? {} : attributes)}
            {...(readOnly ? {} : listeners)}
            aria-label={`Reorder header ${String(index + 1)}`}
          >
            <RhUiGripVerticalFillIcon aria-hidden />
          </Button>
        </FlexItem>
        <FlexItem grow={{ default: 'grow' }} className={styles.headerCard}>
          <Stack hasGutter>
            <StackItem>
              <Flex
                alignItems={{ default: 'alignItemsFlexStart' }}
                gap={{ default: 'gapSm' }}
                flexWrap={{ default: 'nowrap' }}
              >
                <FlexItem>
                  <DisabledWithTooltip isDisabled={hasError} content="Correct header errors before collapsing">
                    <Button
                      type="button"
                      variant="plain"
                      className={styles.toggleButton}
                      aria-label={`${isExpanded ? 'Collapse' : 'Expand'} header ${index + 1}`}
                      aria-expanded={isExpanded}
                      aria-controls={contentId}
                      isAriaDisabled={hasError}
                      onClick={hasError ? undefined : () => setExpanded(!expanded)}
                    >
                      <RhUiCaretDownIcon className={styles.toggleIcon} aria-hidden />
                    </Button>
                  </DisabledWithTooltip>
                </FlexItem>
                <FlexItem grow={{ default: 'grow' }}>
                  <SynTextField
                    name={`headers.${index}.name`}
                    label="Header name"
                    ariaLabel={`${label} name`}
                    isDisabled={readOnly}
                  />
                </FlexItem>
                {!readOnly && (
                  <FlexItem>
                    <Button
                      type="button"
                      variant="plain"
                      icon={<RhUiTrashIcon />}
                      aria-label={`Remove header ${index + 1}`}
                      onClick={onRemove}
                    />
                  </FlexItem>
                )}
              </Flex>
            </StackItem>
            <StackItem id={contentId} hidden={!isExpanded}>
              <KafkaPublishByteFields name={`headers.${index}`} label={label} />
            </StackItem>
          </Stack>
        </FlexItem>
      </Flex>
    </div>
  )
}

const HEADER_SORT_INSTRUCTIONS = {
  draggable:
    'To reorder a header, press Space or Enter to pick it up. Use the up and down arrow keys to move it. Press Space or Enter to drop it, or Escape to cancel.',
}

export function KafkaPublishMessageFields() {
  const {
    control,
    setFocus,
    formState: { errors },
  } = useFormContext<KafkaPublishFormData>()
  const { fields, append, remove, move } = useFieldArray({ control, name: 'headers' })
  const source = useWatch({ control, name: 'headers_mode' })
  const readOnly = useIsVersionView()
  const addButtonRef = useRef<HTMLButtonElement>(null)
  const pendingFocusRef = useRef<HTMLElement | null>(null)
  const [activeDrag, setActiveDrag] = useState<{ id: string; keyboard: boolean } | null>(null)
  const activeIndex = fields.findIndex((field) => field.id === activeDrag?.id)
  const headerError = errors.headers?.root?.message ?? errors.headers?.message
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )
  const positionOf = (id: string | number) => fields.findIndex((field) => field.id === id) + 1
  const announcements: Announcements = {
    onDragStart: ({ active }) => `Picked up header ${positionOf(active.id)} of ${fields.length}.`,
    onDragOver: ({ active, over }) =>
      over ? `Header ${positionOf(active.id)} is over position ${positionOf(over.id)} of ${fields.length}.` : undefined,
    onDragEnd: ({ active, over }) =>
      over
        ? `Header ${positionOf(active.id)} dropped at position ${positionOf(over.id)} of ${fields.length}.`
        : 'Header reorder cancelled.',
    onDragCancel: () => 'Header reorder cancelled.',
  }

  // Moving a keyed DOM node can drop browser focus. Restore it after the move commits.
  useLayoutEffect(() => {
    const target = pendingFocusRef.current
    pendingFocusRef.current = null
    if (target?.isConnected) target.focus()
  }, [fields])

  function removeHeader(index: number) {
    if (fields.length === 1) addButtonRef.current?.focus()
    else setFocus(`headers.${index === 0 ? 1 : index - 1}.name`)
    remove(index)
  }

  function handleDragEnd({ active, over, activatorEvent }: DragEndEvent) {
    setActiveDrag(null)
    if (readOnly || !over || active.id === over.id) return
    const from = fields.findIndex((field) => field.id === active.id)
    const to = fields.findIndex((field) => field.id === over.id)
    if (from !== -1 && to !== -1) {
      if (activatorEvent instanceof KeyboardEvent && activatorEvent.target instanceof HTMLElement) {
        pendingFocusRef.current = activatorEvent.target
      }
      move(from, to)
    }
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <KafkaPublishByteFields name="key" label="Message key" />
      </StackItem>
      <StackItem>
        <FormSection
          title={<FormLabelWithHelp label="Message headers" helpText={KAFKA_PUBLISH_HEADERS_HELP} />}
          titleElement="h3"
        >
          <HelperText>
            <HelperTextItem>Configure headers sent with each Kafka message.</HelperTextItem>
          </HelperText>
          <SynSelectField
            name="headers_mode"
            label="Header source"
            labelHelp={nodeHelp.kafkaPublishHeaderSource}
            options={HEADER_SOURCES}
            isDisabled={readOnly}
          />
          {source === 'template' ? (
            <SynTextAreaField
              name="headers_template"
              label="Headers template"
              rows={3}
              isDisabled={readOnly}
              hint={
                'Use a full-value template, such as ${trigger.payload.headers}, that resolves to an ordered list of header entries.'
              }
            />
          ) : (
            <Stack hasGutter>
              {!readOnly && fields.length > 1 && (
                <StackItem>
                  <HelperText>
                    <HelperTextItem>Drag to reorder headers.</HelperTextItem>
                  </HelperText>
                </StackItem>
              )}
              {fields.length > 0 && (
                <StackItem>
                  <DndContext
                    sensors={sensors}
                    collisionDetection={closestCenter}
                    modifiers={[restrictToVerticalAxis]}
                    accessibility={{ announcements, screenReaderInstructions: HEADER_SORT_INSTRUCTIONS }}
                    onDragStart={({ active, activatorEvent }) =>
                      setActiveDrag({ id: String(active.id), keyboard: activatorEvent instanceof KeyboardEvent })
                    }
                    onDragEnd={handleDragEnd}
                    onDragCancel={() => setActiveDrag(null)}
                  >
                    <SortableContext items={fields.map((field) => field.id)} strategy={verticalListSortingStrategy}>
                      <Stack hasGutter>
                        {fields.map((field, index) => (
                          <StackItem key={field.id}>
                            <SortableHeader
                              fieldId={field.id}
                              index={index}
                              readOnly={readOnly}
                              onRemove={() => removeHeader(index)}
                            />
                          </StackItem>
                        ))}
                      </Stack>
                    </SortableContext>
                    {/* Keyboard collision detection needs the original card's full bounds. */}
                    <DragOverlay dropAnimation={null}>
                      {activeIndex !== -1 && !activeDrag?.keyboard && (
                        <div className={styles.dragOverlay} aria-hidden>
                          <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
                            <FlexItem>
                              <RhUiGripVerticalFillIcon />
                            </FlexItem>
                            <FlexItem>Header {activeIndex + 1}</FlexItem>
                          </Flex>
                        </div>
                      )}
                    </DragOverlay>
                  </DndContext>
                </StackItem>
              )}
              {headerError && (
                <StackItem>
                  <FormFieldError message={headerError} />
                </StackItem>
              )}
              {!readOnly && (
                <StackItem>
                  <Button
                    ref={addButtonRef}
                    type="button"
                    variant="link"
                    icon={<RhUiAddIcon />}
                    isDisabled={fields.length >= KAFKA_MAX_HEADERS}
                    onClick={() =>
                      append({ name: '', encoding: 'utf-8', value: '' }, { focusName: `headers.${fields.length}.name` })
                    }
                  >
                    Add header
                  </Button>
                </StackItem>
              )}
            </Stack>
          )}
        </FormSection>
      </StackItem>
    </Stack>
  )
}
