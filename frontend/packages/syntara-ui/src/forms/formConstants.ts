/** Matches backend `FIELD_NAME_PATTERN` and OpenAPI `value_name` pattern. */
export const FORM_FIELD_VALUE_NAME_MAX_LENGTH = 64
export const FORM_FIELD_LABEL_MAX_LENGTH = 200
export const FORM_DEFINITION_MIN_FIELDS = 1
export const FORM_DEFINITION_MAX_FIELDS = 100
export const FORM_STATIC_OPTIONS_MAX_LENGTH = 500
export const FORM_STATIC_OPTION_LABEL_MAX_LENGTH = 200

function isFieldNameStartChar(code: number): boolean {
  return (code >= 65 && code <= 90) || (code >= 97 && code <= 122) || code === 95
}

function isFieldNameChar(code: number): boolean {
  return isFieldNameStartChar(code) || (code >= 48 && code <= 57)
}

/** Validates `value_name` without regex (Sonar-safe; mirrors OpenAPI pattern). */
export function isValidFormFieldValueName(value: string): boolean {
  if (value.length < 1 || value.length > FORM_FIELD_VALUE_NAME_MAX_LENGTH) {
    return false
  }
  const first = value.codePointAt(0)
  if (first === undefined || !isFieldNameStartChar(first)) {
    return false
  }
  for (let index = 1; index < value.length; index += 1) {
    const code = value.codePointAt(index)
    if (code === undefined || !isFieldNameChar(code)) {
      return false
    }
  }
  return true
}
