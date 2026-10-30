import { Tab, Tabs, TabTitleText } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { useCallback, useEffect, useRef, useState } from 'react'
import { FormProvider, useForm } from 'react-hook-form'

import {
  formDefinitionSchema,
  prepareFormDefinitionForCommit,
  safeParseFormDefinition,
  type FormDefinitionSchemaInput,
} from '../../forms'
import { zodResolver } from '../../routes/builder/node-forms/shared/formSchemaUtils'

import type { FormDefinitionFieldServerError } from './formFieldBuilder/formDefinitionFieldServerError'
import styles from './formFieldBuilder/formFieldBuilder.module.css'
import { FormFieldBuilderCommitContext } from './formFieldBuilder/formFieldBuilderCommitContext'
import { FormFieldBuilderDesignTab } from './formFieldBuilder/FormFieldBuilderDesignTab'
import { FormFieldBuilderJsonSchemaTab } from './formFieldBuilder/FormFieldBuilderJsonSchemaTab'
import type { FormFieldBuilderOptionsMode } from './formFieldBuilder/formFieldBuilderOptionsModeContext'
import { FormFieldBuilderOptionsModeProvider } from './formFieldBuilder/FormFieldBuilderOptionsModeProvider'
import { FormFieldBuilderPreviewTab } from './formFieldBuilder/FormFieldBuilderPreviewTab'
import { useApplyServerFormFieldErrors } from './formFieldBuilder/useApplyServerFormFieldErrors'

type BuilderTab = 'design' | 'preview' | 'json'

export type SynFormFieldBuilderProps = {
  value: FormDefinition
  onChange: (definition: FormDefinition) => void
  isDisabled?: boolean
  /** When true, shows only the field cards (no Design / Preview / JSON tabs). */
  designOnly?: boolean
  /** Restricts dropdown/multi-select fields to static option lists (form triggers). */
  optionsMode?: FormFieldBuilderOptionsMode
  /** API validation errors mapped to `fields.{index}.{subPath}` in the builder form. */
  serverFieldErrors?: ReadonlyArray<FormDefinitionFieldServerError>
  /** Registers flush/read handlers so the parent can sync field edits before submit. */
  registerCommit?: (handlers: { flush: () => void; readPreparedDefinition: () => FormDefinition } | null) => void
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
  optionsMode = 'default',
  serverFieldErrors,
  registerCommit,
}: Readonly<SynFormFieldBuilderProps>) {
  const [activeTab, setActiveTab] = useState<BuilderTab>('design')
  const lastEmittedRef = useRef(JSON.stringify(value))

  const isDraftBuilder = designOnly
  const defaultValues: FormDefinitionSchemaInput = { fields: value.fields }

  const methods = useForm<FormDefinitionSchemaInput, unknown, FormDefinition>({
    resolver: isDraftBuilder ? undefined : zodResolver(formDefinitionSchema),
    mode: isDraftBuilder ? 'onSubmit' : 'onTouched',
    reValidateMode: isDraftBuilder ? 'onSubmit' : 'onChange',
    defaultValues,
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

  useApplyServerFormFieldErrors(methods, serverFieldErrors)

  const commit = useCallback(() => {
    const raw = methods.getValues()
    if (isDraftBuilder) {
      const prepared = prepareFormDefinitionForCommit({ fields: raw.fields })
      const next = JSON.stringify(prepared)
      if (next !== lastEmittedRef.current) {
        lastEmittedRef.current = next
        onChange(prepared)
      }
      return
    }
    // Keep builder toggles as the user set them (e.g. time on, timezone off). API repair runs on publish via
    // prepareFormDefinitionForCommit — do not reset RHF here or checkboxes snap back.
    const parsed = safeParseFormDefinition(raw)
    if (!parsed.success) {
      return
    }
    const next = JSON.stringify(parsed.data)
    if (next !== lastEmittedRef.current) {
      lastEmittedRef.current = next
      onChange(parsed.data)
    }
  }, [isDraftBuilder, methods, onChange])

  const readPreparedDefinition = useCallback((): FormDefinition => {
    const raw = methods.getValues()
    return prepareFormDefinitionForCommit({ fields: raw.fields ?? [] })
  }, [methods])

  useEffect(() => {
    registerCommit?.({ flush: commit, readPreparedDefinition })
    return () => registerCommit?.(null)
  }, [commit, readPreparedDefinition, registerCommit])

  const designTab = (
    <div className={designOnly ? styles.designOnlyPanel : styles.tabPanelBody}>
      <FormFieldBuilderDesignTab isDisabled={isDisabled} hideValidationBanner={isDraftBuilder} />
    </div>
  )

  return (
    <FormProvider {...methods}>
      <FormFieldBuilderOptionsModeProvider mode={optionsMode}>
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
                <div className={styles.tabPanelBody}>
                  <FormFieldBuilderPreviewTab />
                </div>
              </Tab>
              <Tab eventKey="json" title={<TabTitleText>JSON Schema</TabTitleText>}>
                <div className={styles.tabPanelBody}>
                  <FormFieldBuilderJsonSchemaTab isDisabled={isDisabled} />
                </div>
              </Tab>
            </Tabs>
          )}
        </FormFieldBuilderCommitContext>
      </FormFieldBuilderOptionsModeProvider>
    </FormProvider>
  )
}
