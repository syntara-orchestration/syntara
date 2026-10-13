import type { FormsAPI } from '@syntara/contracts'

import { formsClient } from '../../../client'
import { detachPromise } from '../../../utils/detachPromise'

type FormPromptRead = FormsAPI.components['schemas']['FormPromptRead']

function isFormPromptRead(data: unknown): data is FormPromptRead {
  return (
    typeof data === 'object' &&
    data !== null &&
    'id' in data &&
    typeof data.id === 'string' &&
    'form_definition' in data
  )
}

export type FormPromptUrlLookupState = {
  formPrompt: FormPromptRead | undefined
  isLoading: boolean
  isError: boolean
  error: unknown
  refetch: () => void
}

/** Reads `?form_prompt=<id>` and fetches the full form prompt record. */
export function useFetchFormPromptForUrlParam(searchParams: string): FormPromptUrlLookupState {
  const formPromptId = new URLSearchParams(searchParams).get('form_prompt')

  const formPromptQuery = formsClient.useQuery(
    'get',
    '/form_prompts/{form_prompt_id}',
    { params: { path: { form_prompt_id: formPromptId ?? '' } } },
    { enabled: !!formPromptId }
  )

  return {
    formPrompt: isFormPromptRead(formPromptQuery.data) ? formPromptQuery.data : undefined,
    isLoading: formPromptQuery.isLoading,
    isError: formPromptQuery.isError,
    error: formPromptQuery.error,
    refetch: () => {
      detachPromise(formPromptQuery.refetch())
    },
  }
}
