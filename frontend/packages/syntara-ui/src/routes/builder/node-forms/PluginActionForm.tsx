import {
  Content,
  Flex,
  FlexItem,
  FormGroup,
  Label,
  MenuToggle,
  SelectOption,
  Stack,
  StackItem,
  Switch,
} from '@patternfly/react-core'
import type { ReactNode, Ref } from 'react'
import { useMemo, useState } from 'react'
import type { UseFormReturn } from 'react-hook-form'
import { z } from 'zod'

import { SynForm } from '../../../components/forms/SynForm'
import { SynSelect } from '../../../components/SynSelect'
import { useSynForm } from '../../../hooks/useSynForm'
import type { BaseNodeFormProps } from '../registry/NodeRegistry'

import { ActivityNameField } from './shared/ActivityNameField'
import { NodeFormContainer } from './shared/NodeFormContainer'

/** One input property declared by a plugin action's JSON Schema. */
export type PluginInputProperty = {
  name: string
  type?: string
  description?: string
  enumValues?: string[]
  defaultValue?: unknown
  isRequired: boolean
}

/** Everything the form needs to render and label one plugin action. */
export type PluginActionSummary = {
  identity: string
  displayName: string
  description?: string | null
  plugin: string
  pluginVersion?: string
  inputProperties: PluginInputProperty[]
}

export type PluginActionFormData = {
  name?: string
  inputs: Record<string, unknown>
  origin?: string | null
}

/** Raw react-hook-form values: input properties nested under `inputs`. */
type PluginActionFormValues = {
  name: string
  inputs?: Record<string, unknown>
  origin?: string
}

type PluginActionFormProps = BaseNodeFormProps<PluginActionFormData> & {
  action?: PluginActionSummary
}

function buildZodSchema(properties: PluginInputProperty[]) {
  const stepName = z.string().trim().min(1, 'Step name is required').max(255)
  if (properties.length === 0) {
    return z.object({ name: stepName })
  }
  const inputs: Record<string, z.ZodTypeAny> = {}
  for (const property of properties) {
    let field: z.ZodTypeAny
    if (property.enumValues?.length) {
      field = z.string()
    } else if (property.type === 'number' || property.type === 'integer') {
      field = z.coerce.number()
    } else if (property.type === 'boolean') {
      field = z.boolean()
    } else {
      field = z.string()
    }
    inputs[property.name] = property.isRequired ? field : field.optional()
  }
  // Input properties live under a dedicated `inputs` namespace so an action
  // property called `name` can never collide with the step-name field.
  return z.object({
    name: stepName,
    inputs: z.object(inputs).optional(),
    origin: z.string().trim().url('Origin must be a URL, e.g. https://api.example.com').optional().or(z.literal('')),
  })
}

/**
 * Schema-driven configuration form for installed plugin actions.
 *
 * The input fields are derived from the action's declared JSON Schema; the
 * submitted values become the `inputs` of the resulting plugin_action node.
 */
export function PluginActionForm({ onSubmit, initialData, action }: Readonly<PluginActionFormProps>) {
  const properties = useMemo(() => action?.inputProperties ?? [], [action])

  const schema = useMemo(() => buildZodSchema(properties), [properties])
  const defaults = useMemo(() => {
    const inputs: Record<string, unknown> = {}
    for (const property of properties) {
      inputs[property.name] =
        initialData?.inputs?.[property.name] ??
        property.defaultValue ??
        (property.enumValues?.length ? property.enumValues[0] : '')
    }
    return {
      name: initialData?.name ?? action?.displayName ?? 'Plugin step',
      inputs,
      origin: typeof initialData?.origin === 'string' ? initialData.origin : '',
    }
  }, [properties, initialData, action])

  const form = useSynForm<PluginActionFormValues>({ schema, defaultValues: defaults })
  const { handleSubmit } = form

  const submit = (values: { name?: string; inputs?: Record<string, unknown>; origin?: string }) => {
    const inputs: Record<string, unknown> = {}
    for (const property of properties) {
      const value = values.inputs?.[property.name]
      if (value !== undefined && value !== '') {
        inputs[property.name] = value
      }
    }
    const fallbackName = action?.displayName ?? 'Plugin step'
    onSubmit({
      name: typeof values.name === 'string' && values.name ? values.name : fallbackName,
      inputs,
      origin: values.origin?.trim() ? values.origin.trim() : null,
    })
  }

  return (
    <NodeFormContainer formId="plugin-action-form" onSubmit={handleSubmit(submit)}>
      <SynForm form={form}>
        <Stack hasGutter>
          <StackItem>
            <ActivityNameField<never> fieldId="plugin-action-name" placeholder={action?.displayName} />
          </StackItem>
          {action && (
            <StackItem>
              <Flex>
                <FlexItem>
                  <Label variant="outline">{action.plugin}</Label>
                </FlexItem>
                {action.pluginVersion && (
                  <FlexItem>
                    <Label variant="outline">{`v${action.pluginVersion}`}</Label>
                  </FlexItem>
                )}
              </Flex>
            </StackItem>
          )}
          {properties.length > 0 ? (
            properties.map((property) => <PluginInputField key={property.name} property={property} form={form} />)
          ) : (
            <StackItem>This action takes no inputs.</StackItem>
          )}
          <StackItem>
            <FormGroup label="Origin" fieldId="plugin-action-origin">
              <input
                id="plugin-action-origin"
                type="text"
                className="pf-v6-c-form-control"
                placeholder="https://api.example.com (optional)"
                {...form.register('origin')}
              />
              <FieldHint>
                Optional base URL for real HTTP execution. Leave empty to simulate the action through the platform
                runner.
              </FieldHint>
            </FormGroup>
          </StackItem>
        </Stack>
      </SynForm>
    </NodeFormContainer>
  )
}

/** Renders one schema-declared input: text, number, or enum dropdown. */
function PluginInputField({
  property,
  form,
}: {
  property: PluginInputProperty
  form: UseFormReturn<PluginActionFormValues>
}) {
  const [isOpen, setIsOpen] = useState(false)
  const fieldId = `plugin-input-${property.name}`
  const formPath = `inputs.${property.name}` as const
  const value: unknown = form.watch(formPath)

  if (property.enumValues?.length) {
    return (
      <FormGroup label={property.name} fieldId={fieldId} isRequired={property.isRequired}>
        <SynSelect
          aria-label={`Select ${property.name}`}
          isOpen={isOpen}
          onOpenChange={setIsOpen}
          selected={typeof value === 'string' && value ? value : null}
          onSelect={(_event, selection) => {
            form.setValue(formPath, String(selection), { shouldDirty: true })
            setIsOpen(false)
          }}
          toggle={(toggleRef: Ref<HTMLButtonElement>) => (
            <MenuToggle ref={toggleRef} onClick={() => setIsOpen(!isOpen)} isExpanded={isOpen} isFullWidth>
              {typeof value === 'string' && value ? value : 'Select…'}
            </MenuToggle>
          )}
        >
          {property.enumValues.map((option) => (
            <SelectOption key={option} value={option} isSelected={option === value}>
              {option}
            </SelectOption>
          ))}
        </SynSelect>
        {property.description && <FieldHint>{property.description}</FieldHint>}
      </FormGroup>
    )
  }

  if (property.type === 'boolean') {
    const checked = value === true
    return (
      <FormGroup label={property.name} fieldId={fieldId} isRequired={property.isRequired}>
        <Switch
          id={fieldId}
          aria-label={`Toggle ${property.name}`}
          isChecked={checked}
          onChange={(_event, isChecked) => form.setValue(formPath, isChecked, { shouldDirty: true })}
        />
        {property.description && <FieldHint>{property.description}</FieldHint>}
      </FormGroup>
    )
  }

  const inputType = property.type === 'number' || property.type === 'integer' ? 'number' : 'text'
  return (
    <FormGroup label={property.name} fieldId={fieldId} isRequired={property.isRequired}>
      <input id={fieldId} type={inputType} className="pf-v6-c-form-control" {...form.register(formPath)} />
      {property.description && <FieldHint>{property.description}</FieldHint>}
    </FormGroup>
  )
}

function FieldHint({ children }: { children: ReactNode }) {
  return (
    <Content component="p" style={{ fontSize: '0.75rem', color: 'var(--pf-t--global--text--color--subtle, #6a6e73)' }}>
      {children}
    </Content>
  )
}
