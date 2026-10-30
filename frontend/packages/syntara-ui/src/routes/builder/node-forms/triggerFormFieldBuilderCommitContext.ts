import type { FormDefinition } from '@syntara/contracts'
import { createContext, type MutableRefObject } from 'react'

export type TriggerFormFieldBuilderCommitHandlers = {
  flush: () => void
  readPreparedDefinition: () => FormDefinition
}

/** Ref filled by {@link SynFormFieldBuilder} so trigger submit can flush pending field edits. */
export const TriggerFormFieldBuilderCommitRefContext = createContext<
  MutableRefObject<TriggerFormFieldBuilderCommitHandlers | null> | null
>(null)
