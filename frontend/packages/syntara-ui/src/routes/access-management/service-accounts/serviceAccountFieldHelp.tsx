import { createFieldHelp } from '../../../components/createFieldHelp'

import * as T from './serviceAccountFieldHelpText'

/** Pre-built labelHelp elements for service account forms. */
export const serviceAccountHelp = {
  name: createFieldHelp('Name', T.NAME_HELP),
  description: createFieldHelp('Description', T.DESCRIPTION_HELP),
  credentialExpiration: createFieldHelp('Credential expiration date', T.CREDENTIAL_EXPIRATION_HELP),
  gracePeriod: createFieldHelp('Current secret grace period', T.GRACE_PERIOD_HELP),
} as const
