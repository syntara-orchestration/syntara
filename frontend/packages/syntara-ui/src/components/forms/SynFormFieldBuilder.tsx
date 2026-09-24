import { Tab, Tabs, TabTitleText } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { useCallback, useEffect, useRef, useState } from 'react'
import { FormProvider, useForm } from 'react-hook-form'

import { formDefinitionSchema, safeParseFormDefinition, type FormDefinitionSchemaInput } from '../../forms'
import { zodResolver } from '../../routes/builder/node-forms/shared/formSchemaUtils'

import { FormFieldBuilderCommitContext } from './formFieldBuilder/formFieldBuilderCommitContext'
import { FormFieldBuilderDesignTab } from './formFieldBuilder/FormFieldBuilderDesignTab'
import { FormFieldBuilderJsonSchemaTab } from './formFieldBuilder/FormFieldBuilderJsonSchemaTab'
import { FormFieldBuilderPreviewTab } from './formFieldBuilder/FormFieldBuilderPreviewTab'

type BuilderTab = 'design' | 'preview' | 'json'

export type SynFormFieldBuilderProps = {
  value: FormDefinition
  onChange: (definition: FormDefinition) => void
  isDisabled?: boolean
  /** When true, shows only the field cards (no Design / Preview / JSON tabs). */
  designOnly?: boolean
}

/**
 * Visual editor for workflow interactive-prompt form definitions.
 *
 * Intended for workflow builder / prompt configuration once wired by the parent feature.
 * File upload fields are not supported until they are added to the FormDefinition schema.
 */
export function SynFormFieldBuilder({
  value,
  onChange,
  isDisabled,
  designOnly = false,
}: Readonly<SynFormFieldBuilderProps>) {
  const [activeTab, setActiveTab] = useState<BuilderTab>('design')
  const lastEmittedRef = useRef(JSON.stringify(value))

  const methods = useForm<FormDefinitionSchemaInput, unknown, FormDefinition>({
    resolver: zodResolver(formDefinitionSchema),
    mode: 'onTouched',
    reValidateMode: 'onChange',
    defaultValues: value as FormDefinitionSchemaInput,
  })

  const valueKey = JSON.stringify(value)
  useEffect(() => {
    // Parent-controlled value (e.g. workflow node form_definition). Skip reset when this
    // update is our own commit echoing back — otherwise every keystroke resets RHF and drops focus.
    if (valueKey === lastEmittedRef.current) {
      return
    }
    lastEmittedRef.current = valueKey
    methods.reset(JSON.parse(valueKey) as FormDefinitionSchemaInput)
  }, [valueKey, methods])

  const commit = useCallback(() => {
    const parsed = safeParseFormDefinition(methods.getValues())
    if (!parsed.success) {
      return
    }
    const next = JSON.stringify(parsed.data)
    if (next !== lastEmittedRef.current) {
      lastEmittedRef.current = next
      onChange(parsed.data)
    }
  }, [methods, onChange])

  const designTab = <FormFieldBuilderDesignTab isDisabled={isDisabled} />

  return (
    <FormProvider {...methods}>
      <FormFieldBuilderCommitContext value={commit}>
        {designOnly ? (
          designTab
        ) : (
          <Tabs
            activeKey={activeTab}
            onSelect={(_event, tabIndex) => setActiveTab(tabIndex as BuilderTab)}
            aria-label="Form builder views"
          >
            <Tab eventKey="design" title={<TabTitleText>Design</TabTitleText>}>
              {designTab}
            </Tab>
            <Tab eventKey="preview" title={<TabTitleText>Preview</TabTitleText>}>
              <FormFieldBuilderPreviewTab />
            </Tab>
            <Tab eventKey="json" title={<TabTitleText>JSON Schema</TabTitleText>}>
              <FormFieldBuilderJsonSchemaTab />
            </Tab>
          </Tabs>
        )}
      </FormFieldBuilderCommitContext>
    </FormProvider>
  )
}
