import type { CredentialsAPI } from '@syntara/contracts'

/** Sentinel value used by the API to represent encrypted secret fields */
export const ENCRYPTED_SENTINEL = '$encrypted$'

/** Credential resource from the API */
export type Credential = CredentialsAPI.components['schemas']['CredentialRead']

/** Credential type resource from the API */
export type CredentialType = CredentialsAPI.components['schemas']['CredentialTypeRead']

/** Workflow reference returned by the credentials workflows endpoint */
export type CredentialWorkflowRef = CredentialsAPI.components['schemas']['CredentialWorkflowRef']
