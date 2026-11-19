import type { FormsAPI } from '@syntara/contracts'

type FormPromptListRead = FormsAPI.components['schemas']['FormPromptListRead']

/** Form prompt fields the execution detail page tracks, built from `GET /form_prompts` list rows. */
export type FormPromptSummary = Pick<
  FormPromptListRead,
  'id' | 'execution_id' | 'project_id' | 'prompt_node_id' | 'loop_iteration_path' | 'name' | 'status'
>
