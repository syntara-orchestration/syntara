import type { FormDefinition } from '@syntara/contracts'
import { createContext, type MutableRefObject } from 'react'

export type FormFieldBuilderCommitHandlers = {
  flush: () => void
  readPreparedDefinition: () => FormDefinition
}

/** Ref filled by {@link SynFormFieldBuilder} so node submit can flush pending field edits. */
export const FormFieldBuilderCommitRefContext =
  createContext<MutableRefObject<FormFieldBuilderCommitHandlers | null> | null>(null)
