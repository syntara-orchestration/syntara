import { useContext } from 'react'

import { FormFieldBuilderOptionsModeContext } from './formFieldBuilderOptionsModeContext'

export function useFormFieldBuilderOptionsMode() {
  return useContext(FormFieldBuilderOptionsModeContext)
}
