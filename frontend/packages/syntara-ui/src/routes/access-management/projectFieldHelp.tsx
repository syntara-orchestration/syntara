import { createFieldHelp } from '../../components/createFieldHelp'

/** Help popover body text for project create/edit form fields. */
export const PROJECT_NAME_HELP =
  'Projects provide resource isolation. Workflows, credentials, and other project-scoped resources belong to one project. Users can hold different roles in different projects.'

/** Pre-built labelHelp elements for project forms. */
export const projectHelp = {
  name: createFieldHelp('Project name', PROJECT_NAME_HELP),
} as const
