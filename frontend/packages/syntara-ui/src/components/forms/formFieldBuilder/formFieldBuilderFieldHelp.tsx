import type { ReactElement } from 'react'

import { FieldHelpPopover } from '../../FieldHelpPopover'

/** Label-help copy for SynFormFieldBuilder field settings. */
const FORM_FIELD_BUILDER_LABEL_HELP = {
  label:
    'Shown to the person filling out the form, above the field. This is different from the value name below, which downstream workflow steps use to reference the submitted value.',
  checkboxLabel:
    'Text shown beside the checkbox for the person filling out the form. This is different from the value name below, which downstream workflow steps use to reference the submitted value.',
  valueName: 'Downstream nodes reference this value as ${trigger.<name>}.',
  placeholder:
    'Example text shown inside the field before the person filling out the form enters a value. It disappears once they start typing and is never submitted as data.',
  helpText: 'Extra guidance shown below the field to help the person filling out the form understand what to enter.',
  defaultValue: 'The answer or selection prefilled when the form opens. The user can change it before submitting.',
  dateShowInForm:
    'Choose which date, time, and timezone inputs appear in the form. At least one input must be selected.',
  optionsSource:
    'Choose static to define a fixed list of options, or dynamic to populate options from a template expression at form render time.',
  dynamicOptionsExpression:
    'Template expression that resolves to an array of { label, value } objects when the form is rendered. Drag input parameters from the Input panel to build the expression.',
  dynamicOptionsLabelKey: 'Property name used for the option label when the expression returns a list of objects.',
  dynamicOptionsValueKey: 'Property name used for the option value when the expression returns a list of objects.',
  optionDisplayLabel:
    'Text shown in the dropdown for the person filling out the form. This is the option label they read and select.',
  optionValueName:
    'Value stored when this option is selected. Downstream workflow steps reference this value, not the option label.',
} as const

export type FormFieldBuilderLabelHelpKey = keyof typeof FORM_FIELD_BUILDER_LABEL_HELP

export function formFieldBuilderLabelHelp(
  key: FormFieldBuilderLabelHelpKey,
  headerContent: string
): ReactElement | undefined {
  const helpText = FORM_FIELD_BUILDER_LABEL_HELP[key].trim()
  if (helpText.length === 0) {
    return undefined
  }
  return <FieldHelpPopover headerContent={headerContent} helpText={helpText} />
}
