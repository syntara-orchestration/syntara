import { FormGroup, ToggleGroup, ToggleGroupItem } from '@patternfly/react-core'
import type { FormDefinition, FormField } from '@syntara/contracts'
import { useFormContext } from 'react-hook-form'

import { FormFieldTypeEnum } from '../../../forms'
import { SynTextField } from '../SynTextField'

import { defaultDynamicOptionsSource, defaultStaticOptionsSource } from './createDefaultField'
import styles from './formFieldBuilder.module.css'
import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'
import { FORM_FIELD_BUILDER_LABEL_HELP, formFieldBuilderLabelHelp } from './formFieldBuilderFieldHelp'
import { StaticOptionsEditor } from './StaticOptionsEditor'

type FormFieldBuilderOptionsSectionProps = {
  index: number
  field: Extract<FormField, { type: typeof FormFieldTypeEnum.DROPDOWN | typeof FormFieldTypeEnum.MULTI_SELECT }>
  isDisabled?: boolean
  idPrefix: string
}

function OptionsSourceToggle({
  source,
  isDisabled,
  onSelectStatic,
  onSelectDynamic,
  idPrefix,
}: Readonly<{
  source: 'static' | 'dynamic'
  isDisabled?: boolean
  onSelectStatic: () => void
  onSelectDynamic: () => void
  idPrefix: string
}>) {
  const staticId = `${idPrefix}-options-static`
  const dynamicId = `${idPrefix}-options-dynamic`

  return (
    <ToggleGroup aria-label="Options source" isCompact>
      <ToggleGroupItem
        text="Static"
        buttonId={staticId}
        isSelected={source === 'static'}
        isDisabled={isDisabled}
        onChange={onSelectStatic}
      />
      <ToggleGroupItem
        text="Dynamic"
        buttonId={dynamicId}
        isSelected={source === 'dynamic'}
        isDisabled={isDisabled}
        onChange={onSelectDynamic}
      />
    </ToggleGroup>
  )
}

export function FormFieldBuilderOptionsSection({
  index,
  field,
  isDisabled,
  idPrefix,
}: Readonly<FormFieldBuilderOptionsSectionProps>) {
  const commit = useFormFieldBuilderCommit()
  const { control, setValue, clearErrors } = useFormContext<FormDefinition>()
  const optionsSource = field.options.source

  return (
    <FormGroup
      label="Options source"
      fieldId={`${idPrefix}-options`}
      labelHelp={formFieldBuilderLabelHelp('optionsSource', 'Options source')}
    >
      <OptionsSourceToggle
        source={optionsSource}
        isDisabled={isDisabled}
        idPrefix={idPrefix}
        onSelectStatic={() => {
          setValue(`fields.${index}.options`, defaultStaticOptionsSource(), { shouldValidate: false })
          commit()
        }}
        onSelectDynamic={() => {
          setValue(`fields.${index}.options`, defaultDynamicOptionsSource(), { shouldValidate: false })
          setValue(`fields.${index}.default`, null, { shouldValidate: false })
          clearErrors(`fields.${index}.options.expression`)
          commit()
        }}
      />
      {optionsSource === 'static' ? (
        <StaticOptionsEditor fieldIndex={index} isDisabled={isDisabled} />
      ) : (
        <div className={styles.optionsDynamicExpression}>
          <SynTextField
            name={`fields.${index}.options.expression`}
            control={control}
            label="Dynamic options expression"
            fieldId={`${idPrefix}-expression`}
            isRequired
            isDisabled={isDisabled}
            placeholder="e.g. ${trigger.environments}"
            hint={FORM_FIELD_BUILDER_LABEL_HELP.dynamicOptionsExpression}
            onValueChange={commit}
          />
        </div>
      )}
    </FormGroup>
  )
}
