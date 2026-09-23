import { createFieldHelp } from '../../../components/createFieldHelp'

import * as T from './userFieldHelpText'

/** Pre-built labelHelp elements for user forms. */
export const userHelp = {
  username: createFieldHelp('Username', T.USERNAME_HELP),
  email: createFieldHelp('Email', T.EMAIL_HELP),
  emailCreate: createFieldHelp('Email', T.EMAIL_CREATE_HELP),
  emailFederatedEdit: createFieldHelp('Email', T.EMAIL_FEDERATED_EDIT_HELP),
  groups: createFieldHelp('Groups', T.GROUPS_HELP),
  status: createFieldHelp('Status', T.STATUS_HELP),
} as const
