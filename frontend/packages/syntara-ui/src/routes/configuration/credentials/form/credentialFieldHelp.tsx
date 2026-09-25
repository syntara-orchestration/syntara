import { createFieldHelp } from '../../../../components/createFieldHelp'

export const credentialHelp = {
  name: createFieldHelp(
    'Name',
    'A unique, descriptive name for this credential. Use a name that helps identify its purpose, such as "Production API Key" or "Dev SSH Key".'
  ),
  description: createFieldHelp(
    'Description',
    'An optional description to provide additional context about this credential, such as what systems it accesses or any usage restrictions.'
  ),
  project: createFieldHelp(
    'Project',
    'The project this credential belongs to. Credentials are scoped to a single project and can only be used by workflows within that project.'
  ),
}
