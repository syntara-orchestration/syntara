import { FormFieldTypeEnum, type FormFieldType } from '@syntara/contracts'

export { FormFieldTypeEnum, type FormFieldType }

/** All supported field type discriminator values (for selects, guards, etc.). */
export const FORM_FIELD_TYPE_VALUES = Object.values(FormFieldTypeEnum) as FormFieldType[]
