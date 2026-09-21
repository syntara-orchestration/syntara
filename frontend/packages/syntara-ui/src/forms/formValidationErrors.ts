/** Error codes aligned with backend `FormFieldError.code` values. */
export type FormFieldErrorCode =
  | 'required'
  | 'type'
  | 'invalid_format'
  | 'must_be_checked'
  | 'not_in_options'
  | 'unknown_field'
  | 'invalid_default'

export type FormFieldValidationError = {
  field: string
  label: string
  code: FormFieldErrorCode
  message: string
}

export class FormDataValidationError extends Error {
  readonly errors: readonly FormFieldValidationError[]

  constructor(errors: readonly FormFieldValidationError[]) {
    super('Form data validation failed')
    this.name = 'FormDataValidationError'
    this.errors = errors
  }
}

export class FormDefinitionValidationError extends Error {
  readonly errors: readonly FormFieldValidationError[]

  constructor(errors: readonly FormFieldValidationError[]) {
    super('Form definition validation failed')
    this.name = 'FormDefinitionValidationError'
    this.errors = errors
  }
}
