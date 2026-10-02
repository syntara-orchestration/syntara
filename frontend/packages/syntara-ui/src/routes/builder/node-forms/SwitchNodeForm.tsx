import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { restrictToVerticalAxis } from '@dnd-kit/modifiers'
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  Alert,
  Button,
  Content,
  ExpandableSection,
  Flex,
  FlexItem,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  TextInput,
  Tooltip,
} from '@patternfly/react-core'
import {
  RhMicronsCaretDownIcon,
  RhUiAddCircleIcon,
  RhUiGripVerticalFillIcon,
  RhUiTrashIcon,
} from '@patternfly/react-icons'
import type { ReactNode } from 'react'
import { useCallback, use, useEffect, useMemo, useRef, useState } from 'react'
import type { Control } from 'react-hook-form'
import { Controller, useFieldArray, useFormContext } from 'react-hook-form'

import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { ExpressionBuilderCore as ExpressionBuilder } from '../../../components/expressions/ExpressionBuilderCore'
import { SynForm } from '../../../components/forms/SynForm'
import { useSynForm } from '../../../hooks/useSynForm'
import type { Expression } from '../../../utils/expressions/types'
import { generateUUID } from '../../../utils/generateUUID'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useIsVersionView } from '../VersionViewContext'

import { ActivityNameField } from './shared/ActivityNameField'
import { nodeHelp } from './shared/nodeFieldHelp'
import { SWITCH_FALLBACK_HELP } from './shared/nodeFieldHelpText'
import { NodeFormContainer } from './shared/NodeFormContainer'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { PathExpressionHelp } from './shared/PathExpressionHelp'
import { switchFormSchema, type SwitchFormData, type SwitchCaseData } from './switchFormSchema'
import styles from './SwitchNodeForm.module.css'

export type { SwitchFormData }

type CaseExpressionFieldProps = {
  fieldId: string
  currentCase: SwitchCaseData
  onFieldChange: (value: SwitchCaseData) => void
  hasError: boolean
}

function CaseExpressionField({ fieldId, currentCase, onFieldChange, hasError }: CaseExpressionFieldProps) {
  const handleChange = useCallback(
    (val: string, tree?: Expression | null, mode?: 'visual' | 'raw') => {
      onFieldChange({
        ...currentCase,
        condition: val,
        expressionTree: tree?.root ? tree : undefined,
        editorMode: mode,
      })
    },
    [onFieldChange, currentCase]
  )

  return (
    <ExpressionBuilder
      id={`case-condition-${fieldId}`}
      value={currentCase?.condition ?? ''}
      initialExpression={currentCase?.expressionTree}
      initialMode={currentCase?.editorMode}
      onChange={handleChange}
      error={hasError}
      placeholder="Build your condition"
    />
  )
}

const MIN_CASES = 1
const MAX_CASES = 100

function createEmptyCase(index: number) {
  return {
    caseId: generateUUID(),
    label: `Path ${index + 1}`,
    condition: '',
  }
}

type SwitchNodeFormProps = {
  onSubmit: (data: SwitchFormData) => void
  initialData?: Partial<SwitchFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
}

type SwitchCaseHeaderProps = {
  index: number
  label: string
  isExpanded: boolean
  hasError: boolean
  canRemove: boolean
  contentId: string
  isDisabled?: boolean
  onToggleExpanded: () => void
  onRemove: () => void
  onLabelChange: (value: string) => void
}

function SwitchCaseHeader({
  index,
  label,
  isExpanded,
  hasError,
  canRemove,
  contentId,
  isDisabled,
  onToggleExpanded,
  onRemove,
  onLabelChange,
}: SwitchCaseHeaderProps) {
  return (
    <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
      <FlexItem>
        <DisabledWithTooltip isDisabled={hasError} content="Fill in all required fields before collapsing">
          <Button
            variant="plain"
            className={styles.toggleButton}
            aria-expanded={isExpanded}
            aria-controls={contentId}
            isAriaDisabled={hasError}
            onClick={hasError ? undefined : onToggleExpanded}
            aria-label={`${isExpanded ? 'Collapse' : 'Expand'} path ${index + 1}`}
          >
            <RhMicronsCaretDownIcon className={styles.toggleIcon} />
          </Button>
        </DisabledWithTooltip>
      </FlexItem>
      <FlexItem grow={{ default: 'grow' }}>
        <FormGroup label="Path name" labelHelp={nodeHelp.switchPathName} fieldId={`case-label-${index}`}>
          <TextInput
            value={label}
            onChange={(_event, val) => onLabelChange(val)}
            aria-label={`Path ${index + 1} name`}
            placeholder={`Path ${index + 1}`}
            isDisabled={isDisabled}
          />
        </FormGroup>
      </FlexItem>
      {canRemove && !isDisabled && (
        <FlexItem>
          <Button variant="plain" isDanger onClick={onRemove} aria-label={`Remove path ${index + 1}`} size="sm">
            <RhUiTrashIcon />
          </Button>
        </FlexItem>
      )}
    </Flex>
  )
}

type SwitchCaseItemProps = {
  fieldId: string
  index: number
  control: Control<SwitchFormData>
  canRemove: boolean
  expandedPaths: Record<string, boolean>
  hadErrorRef: React.MutableRefObject<Record<string, boolean>>
  isDisabled?: boolean
  onToggleExpanded: () => void
  onRemove: () => void
}

function SwitchCaseItem({
  fieldId,
  index,
  control,
  canRemove,
  hadErrorRef,
  expandedPaths,
  isDisabled,
  onToggleExpanded,
  onRemove,
}: SwitchCaseItemProps) {
  const contentId = `case-content-${fieldId}`
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: fieldId })

  const sortableStyle = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div ref={setNodeRef} style={sortableStyle} className={isDragging ? styles.dragging : undefined}>
      <Controller
        control={control}
        name={`cases.${index}`}
        render={({ field, fieldState }) => {
          const currentCase = field.value
          const conditionError = (fieldState.error as Record<string, { message?: string }> | undefined)?.condition
          const hasError = !!fieldState.error
          if (hasError && expandedPaths[fieldId] === false) {
            hadErrorRef.current[fieldId] = true
          }
          const overrideCollapse = hadErrorRef.current[fieldId] === true
          const isExpanded = hasError || overrideCollapse || (expandedPaths[fieldId] ?? true)

          return (
            <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsFlexStart' }}>
              <FlexItem>
                <Button
                  variant="plain"
                  className={styles.dragHandle}
                  aria-label={`Reorder path ${index + 1}`}
                  isDisabled={isDisabled}
                  {...(isDisabled ? {} : listeners)}
                  {...(isDisabled ? {} : attributes)}
                >
                  <RhUiGripVerticalFillIcon />
                </Button>
              </FlexItem>
              <FlexItem grow={{ default: 'grow' }}>
                <Stack hasGutter>
                  <StackItem>
                    <SwitchCaseHeader
                      index={index}
                      label={currentCase?.label ?? ''}
                      isExpanded={isExpanded}
                      hasError={hasError}
                      canRemove={canRemove}
                      contentId={contentId}
                      isDisabled={isDisabled}
                      onToggleExpanded={onToggleExpanded}
                      onRemove={onRemove}
                      onLabelChange={(val) => field.onChange({ ...currentCase, label: val })}
                    />
                  </StackItem>

                  {isExpanded && (
                    <StackItem id={contentId}>
                      <FormGroup
                        label="Path expression"
                        labelHelp={<PathExpressionHelp />}
                        isRequired
                        fieldId={`case-condition-${fieldId}`}
                      >
                        <fieldset disabled={isDisabled} className={nodeFormStyles.disabledFieldset}>
                          <CaseExpressionField
                            fieldId={fieldId}
                            currentCase={currentCase}
                            onFieldChange={field.onChange}
                            hasError={hasError}
                          />
                        </fieldset>
                        {conditionError?.message && (
                          <FormHelperText>
                            <HelperText>
                              <HelperTextItem variant="error">{conditionError.message}</HelperTextItem>
                            </HelperText>
                          </FormHelperText>
                        )}
                      </FormGroup>
                    </StackItem>
                  )}
                </Stack>
              </FlexItem>
            </Flex>
          )
        }}
      />
    </div>
  )
}

function SwitchFormFields({ onHeaderContentChange }: { onHeaderContentChange?: (content: ReactNode | null) => void }) {
  const isVersionView = useIsVersionView()
  const { control } = useFormContext<SwitchFormData>()

  const { fields, append, remove, move } = useFieldArray({ control, name: 'cases' })
  const [expandedPaths, setExpandedPaths] = useState<Record<string, boolean>>({})
  const [fallbackExpanded, setFallbackExpanded] = useState(true)
  const hadErrorRef = useRef<Record<string, boolean>>({})

  const [activeId, setActiveId] = useState<string | null>(null)
  const sensors = useSensors(useSensor(PointerSensor), useSensor(KeyboardSensor))

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveId(null)
    const { active, over } = event
    if (over && active.id !== over.id) {
      const oldIndex = fields.findIndex((f) => f.id === active.id)
      const newIndex = fields.findIndex((f) => f.id === over.id)
      if (oldIndex !== -1 && newIndex !== -1) {
        move(oldIndex, newIndex)
      }
    }
  }

  const activeField = useMemo(() => (activeId ? fields.find((f) => f.id === activeId) : null), [activeId, fields])
  const activeIndex = useMemo(() => (activeId ? fields.findIndex((f) => f.id === activeId) : -1), [activeId, fields])

  const nameField = useMemo(
    () => <ActivityNameField control={control} fieldId="switch-name" ariaLabel="Name" />,
    [control]
  )

  useEffect(() => {
    onHeaderContentChange?.(nameField)
    return () => {
      onHeaderContentChange?.(null)
    }
  }, [nameField, onHeaderContentChange])

  const handleAddPath = () => {
    if (fields.length < MAX_CASES) {
      append(createEmptyCase(fields.length))
    }
  }

  const handleRemovePath = (index: number) => {
    if (fields.length > MIN_CASES) {
      remove(index)
    }
  }

  const parametersContent = (
    <Stack hasGutter>
      {!onHeaderContentChange && (
        <StackItem>
          <ActivityNameField fieldId="switch-name" />
        </StackItem>
      )}

      <StackItem>
        <Alert
          variant="info"
          isExpandable
          isInline
          title="Only one path runs per execution"
          className={nodeFormStyles.compactAlert}
        >
          <Content component="p">
            The workflow evaluates paths in order and follows the first match. All other paths are skipped. Drag to
            reorder paths by evaluation priority.
          </Content>
        </Alert>
      </StackItem>

      <StackItem>
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          modifiers={[restrictToVerticalAxis]}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
        >
          <SortableContext items={fields.map((f) => f.id)} strategy={verticalListSortingStrategy}>
            <Stack hasGutter>
              {fields.map((field, index) => (
                <StackItem key={field.id}>
                  <SwitchCaseItem
                    fieldId={field.id}
                    index={index}
                    control={control}
                    canRemove={fields.length > MIN_CASES}
                    expandedPaths={expandedPaths}
                    hadErrorRef={hadErrorRef}
                    isDisabled={isVersionView}
                    onToggleExpanded={() => {
                      hadErrorRef.current[field.id] = false
                      setExpandedPaths((prev) => ({ ...prev, [field.id]: !(prev[field.id] ?? true) }))
                    }}
                    onRemove={() => handleRemovePath(index)}
                  />
                </StackItem>
              ))}
            </Stack>
          </SortableContext>
          <DragOverlay>
            {activeField && (
              <div className={styles.dragOverlay}>
                <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
                  <FlexItem>
                    <RhUiGripVerticalFillIcon />
                  </FlexItem>
                  <FlexItem grow={{ default: 'grow' }}>{activeField.label || `Path ${activeIndex + 1}`}</FlexItem>
                </Flex>
              </div>
            )}
          </DragOverlay>
        </DndContext>
      </StackItem>

      {!isVersionView && (
        <StackItem>
          <Flex>
            <FlexItem>
              {fields.length >= MAX_CASES ? (
                <Tooltip content="Maximum of 100 paths reached.">
                  <Button variant="link" icon={<RhUiAddCircleIcon />} isDisabled>
                    Add path
                  </Button>
                </Tooltip>
              ) : (
                <Button variant="link" icon={<RhUiAddCircleIcon />} onClick={handleAddPath}>
                  Add path
                </Button>
              )}
            </FlexItem>
          </Flex>
        </StackItem>
      )}

      <StackItem>
        <FormGroup label="Fallback path" labelHelp={nodeHelp.switchFallback} fieldId="switch-fallback-path">
          <ExpandableSection
            toggleText="Fallback path details"
            isIndented
            isExpanded={fallbackExpanded}
            onToggle={(_event, expanded) => setFallbackExpanded(expanded)}
          >
            <Content component="p">{SWITCH_FALLBACK_HELP}</Content>
          </ExpandableSection>
        </FormGroup>
      </StackItem>
    </Stack>
  )

  return <NodeFormTabsLayout parametersContent={parametersContent} />
}

export function SwitchNodeForm(props: SwitchNodeFormProps) {
  const defaultCases = props.initialData?.cases?.length
    ? props.initialData.cases
    : [createEmptyCase(0), createEmptyCase(1)]

  const defaultValues: SwitchFormData = {
    name: props.initialData?.name ?? '',
    cases: defaultCases,
  }

  const form = useSynForm({
    schema: switchFormSchema,
    defaultValues,
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, form, props.onSubmit)

  useEffect(() => {
    form.reset(defaultValues)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset when initialData identity changes
  }, [props.initialData])

  return (
    <NodeFormContainer formId="switch-node-form" onSubmit={form.handleSubmit(props.onSubmit)}>
      <SynForm form={form}>
        <SwitchFormFields onHeaderContentChange={props.onHeaderContentChange} />
      </SynForm>
    </NodeFormContainer>
  )
}
