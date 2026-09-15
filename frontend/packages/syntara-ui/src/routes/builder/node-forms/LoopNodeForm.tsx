import {
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  TextInput,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import type { ReactNode } from 'react'
import { use, useEffect, useMemo, useState } from 'react'
import { Controller, FormProvider, useForm, useFormContext, useWatch } from 'react-hook-form'

import { ExpressionBuilderCore as ExpressionBuilder } from '../../../components/expressions/ExpressionBuilderCore'
import { SynSelect } from '../../../components/SynSelect'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useWorkflowEngineDefaults } from '../hooks/useWorkflowEngineDefaults'
import { useIsVersionView } from '../VersionViewContext'

import { loopFormSchema, type LoopFormData } from './loopFormSchema'
import { ActivityNameField } from './shared/ActivityNameField'
import { conditionValidationRules } from './shared/conditionValidation'
import { zodResolver } from './shared/formSchemaUtils'
import { LoopTypeHelp } from './shared/LoopTypeHelp'
import { MaxIterationsHelp } from './shared/MaxIterationsHelp'
import { nodeHelp } from './shared/nodeFieldHelp'
import { NodeFormContainer } from './shared/NodeFormContainer'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { NodeSettingsForm } from './shared/NodeSettingsForm'
import { WhileConditionHelp } from './shared/WhileConditionHelp'

export type { LoopFormData }

function LoopTypeSelect({
  value,
  onChange,
  isDisabled,
}: {
  value: string
  onChange: (value: string) => void
  isDisabled?: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  return (
    <SynSelect
      id="loop-type"
      isOpen={isOpen}
      selected={value}
      onSelect={(_event, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          isDisabled={isDisabled}
          aria-label="Type"
        >
          {value === 'while' ? 'While' : 'For each'}
        </MenuToggle>
      )}
    >
      <SelectList>
        <SelectOption value="while">While</SelectOption>
        <SelectOption value="forEach">For each</SelectOption>
      </SelectList>
    </SynSelect>
  )
}

type LoopNodeFormProps = {
  onSubmit: (data: LoopFormData) => void
  initialData?: Partial<LoopFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
}

function LoopFormFields({
  onHeaderContentChange,
  validationErrors,
}: {
  onHeaderContentChange?: (content: ReactNode | null) => void
  validationErrors?: {
    items?: { message?: string }
    condition?: { message?: string }
    maxIterations?: { message?: string }
  }
}) {
  const {
    register,
    control,
    formState: { errors: contextErrors },
  } = useFormContext<LoopFormData>()
  const isVersionView = useIsVersionView()
  const errors = validationErrors ?? contextErrors
  const type = useWatch({ control, name: 'type' })
  const { defaults } = useWorkflowEngineDefaults()
  const maxIterDefault = defaults?.maxLoopIterations ?? null

  useEffect(() => {
    if (errors.items) document.getElementById('loop-items')?.focus()
    else if (errors.condition) document.getElementById('loop-condition-while')?.focus()
    else if (errors.maxIterations) document.getElementById('loop-maxIterations')?.focus()
  }, [errors.items, errors.condition, errors.maxIterations])

  const nameField = useMemo(
    () => <ActivityNameField register={register} fieldId="loop-name" ariaLabel="Name" />,
    [register]
  )

  useEffect(() => {
    onHeaderContentChange?.(nameField)
    return () => {
      onHeaderContentChange?.(null)
    }
  }, [nameField, onHeaderContentChange])

  const parametersContent = (
    <Stack hasGutter>
      {!onHeaderContentChange && <ActivityNameField register={register} fieldId="loop-name" />}

      <StackItem>
        <FormGroup label="Type" labelHelp={<LoopTypeHelp />} fieldId="loop-type">
          <Controller
            control={control}
            name="type"
            render={({ field }) => (
              <LoopTypeSelect value={field.value} onChange={field.onChange} isDisabled={isVersionView} />
            )}
          />
        </FormGroup>
      </StackItem>

      {type === 'forEach' && (
        <>
          <StackItem>
            <FormGroup label="Items expression" labelHelp={nodeHelp.loopItems} isRequired fieldId="loop-items">
              <TextInput
                {...register('items')}
                id="loop-items"
                placeholder="${trigger.item_list}"
                style={{ fontFamily: 'monospace' }}
                type="text"
                validated={errors.items ? 'error' : 'default'}
                isDisabled={isVersionView}
              />
              <FormHelperText>
                <HelperText>
                  {errors.items ? (
                    <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                      {errors.items.message}
                    </HelperTextItem>
                  ) : (
                    <HelperTextItem>Expression that evaluates to a list</HelperTextItem>
                  )}
                </HelperText>
              </FormHelperText>
            </FormGroup>
          </StackItem>

          <StackItem>
            <FormGroup label="Item variable" labelHelp={nodeHelp.loopItemVariable} fieldId="loop-itemVariable">
              <TextInput
                {...register('itemVariable')}
                id="loop-itemVariable"
                placeholder="item"
                style={{ fontFamily: 'monospace' }}
                type="text"
                isDisabled={isVersionView}
              />
            </FormGroup>
          </StackItem>

          <StackItem>
            <FormGroup label="Index variable" labelHelp={nodeHelp.loopIndexVariable} fieldId="loop-indexVariable">
              <TextInput
                {...register('indexVariable')}
                id="loop-indexVariable"
                placeholder="index"
                style={{ fontFamily: 'monospace' }}
                type="text"
                isDisabled={isVersionView}
              />
            </FormGroup>
          </StackItem>
        </>
      )}

      <StackItem>
        <FormGroup label="Max iterations" labelHelp={<MaxIterationsHelp />} fieldId="loop-maxIterations">
          <TextInput
            {...register('maxIterations', { valueAsNumber: true })}
            id="loop-maxIterations"
            type="number"
            min={1}
            step={1}
            placeholder={maxIterDefault !== null ? `${String(maxIterDefault)} — system default` : 'System default'}
            style={{ width: '100%' }}
            validated={errors.maxIterations ? 'error' : 'default'}
            isDisabled={isVersionView}
          />
          {errors.maxIterations && (
            <FormHelperText>
              <HelperText>
                <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                  {errors.maxIterations.message}
                </HelperTextItem>
              </HelperText>
            </FormHelperText>
          )}
        </FormGroup>
      </StackItem>

      {type === 'while' && (
        <StackItem>
          <FormGroup
            label="Conditional expression"
            labelHelp={<WhileConditionHelp />}
            isRequired
            fieldId="loop-condition-while"
          >
            <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
              <Controller
                control={control}
                name="condition"
                rules={conditionValidationRules}
                render={({ field, fieldState }) => {
                  const conditionError = fieldState.error ?? errors.condition
                  return (
                    <>
                      <ExpressionBuilder
                        id="loop-condition-while"
                        value={field.value ?? ''}
                        onChange={field.onChange}
                        error={!!conditionError}
                        placeholder="Build your condition"
                      />
                      <FormHelperText>
                        <HelperText>
                          {conditionError ? (
                            <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                              {conditionError.message}
                            </HelperTextItem>
                          ) : (
                            <HelperTextItem>
                              Build your condition using the visual builder or custom expression
                            </HelperTextItem>
                          )}
                        </HelperText>
                      </FormHelperText>
                    </>
                  )
                }}
              />
            </fieldset>
          </FormGroup>
        </StackItem>
      )}
    </Stack>
  )

  const settingsContent = <NodeSettingsForm supportsTimeout={false} supportsRetryPolicy={false} />

  return <NodeFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
}

export function LoopNodeForm(props: LoopNodeFormProps) {
  const defaultValues: LoopFormData = {
    name: '',
    type: 'while',
    indexVariable: 'index',
    itemVariable: 'item',
    settings: {},
    ...props.initialData,
  }

  const validMaxIterations = (value: number | undefined) =>
    typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : undefined

  const handleSubmit = (data: LoopFormData) => {
    const maxIter = validMaxIterations(data.maxIterations)
    const cleanedData: LoopFormData = {
      name: data.name,
      type: data.type,
      settings: data.settings,
      ...(maxIter !== undefined && { maxIterations: maxIter }),
      ...(data.type === 'forEach' && {
        items: data.items,
        indexVariable: data.indexVariable,
        itemVariable: data.itemVariable,
      }),
      ...(data.type === 'while' && {
        condition: data.condition,
      }),
    }
    props.onSubmit(cleanedData)
  }

  const methods = useForm<LoopFormData>({
    resolver: zodResolver(loopFormSchema, undefined, { mode: 'sync' }),
    defaultValues,
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, handleSubmit)

  const {
    formState: { errors },
  } = methods

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="loop-node-form" onSubmit={methods.handleSubmit(handleSubmit)}>
        <LoopFormFields onHeaderContentChange={props.onHeaderContentChange} validationErrors={errors} />
      </NodeFormContainer>
    </FormProvider>
  )
}
