/** Server validation targeting a single row in `form_definition.fields`. */
export type FormDefinitionFieldServerError = {
  fieldIndex: number
  /** Dot path under the field, e.g. `label`, `options`, `default.date`; empty when the whole field failed. */
  subPath: string
  message: string
}
