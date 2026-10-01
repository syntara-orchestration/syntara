import type { ReactElement } from 'react'
import type { FieldValues, Path } from 'react-hook-form'

import { SynExpressionField } from '../../../components/forms/SynExpressionField'
import { useIsVersionView } from '../VersionViewContext'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'
import type { AAPWorkflowTemplateFormData } from './aapWorkflowTemplateSchema'

const EXPRESSION_HINT = 'Enter a value or drag an expression from the Input panel'

/**
 * Generic expression text field with drag-and-drop support.
 * Used for AAP job template and workflow template forms.
 */
type GenericExpressionTextFieldProps<T extends FieldValues> = {
  readonly name: Path<T>
  readonly id: string
  readonly label: string
  readonly placeholder: string
  readonly isRequired?: boolean
  readonly labelHelp?: ReactElement
}

function GenericExpressionTextField<T extends FieldValues>({
  name,
  id,
  label,
  placeholder,
  isRequired,
  labelHelp,
}: GenericExpressionTextFieldProps<T>) {
  const isVersionView = useIsVersionView()

  return (
    <SynExpressionField
      name={name}
      fieldId={id}
      label={label}
      placeholder={placeholder}
      isRequired={isRequired}
      labelHelp={labelHelp}
      hint={EXPRESSION_HINT}
      isDisabled={isVersionView}
    />
  )
}

/**
 * Expression text field for AAP job template forms.
 * Supports drag-and-drop expressions from the Input panel.
 */
export function ExpressionTextField(props: GenericExpressionTextFieldProps<AAPJobTemplateFormData>) {
  return <GenericExpressionTextField {...props} />
}

/**
 * Expression text field for AAP workflow template forms.
 * Supports drag-and-drop expressions from the Input panel.
 */
export function WorkflowExpressionTextField(props: GenericExpressionTextFieldProps<AAPWorkflowTemplateFormData>) {
  return <GenericExpressionTextField {...props} />
}
