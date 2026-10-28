/** Shown in the form builder when a date and timezone are included without a time. */
export const DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE =
  'Select a time when both a date and timezone are included.'

/** When an initial answer includes date parts the field does not collect. */
export function dateDefaultSuppliesExtraComponentsMessage(components: readonly string[]): string {
  return `Default supplies ${components.join(', ')}, which this field does not collect`
}
