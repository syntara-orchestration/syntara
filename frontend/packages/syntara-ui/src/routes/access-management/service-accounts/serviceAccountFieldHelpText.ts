/** Help popover body text for service account create/edit/rotate form fields. */

export const NAME_HELP =
  'A human-readable name for this service account. Use a name that identifies its purpose, such as "CI Pipeline" or "Monitoring Bot."'

export const DESCRIPTION_HELP =
  'Optional details about what this service account is used for, which systems call it, or who manages it.'

export const CREDENTIAL_EXPIRATION_HELP =
  'Date when this credential stops working. Required when creating a credential. Must fall within the maximum allowed lifetime shown below the field. After this date, token requests with this client ID and secret are rejected.'

export const GRACE_PERIOD_HELP =
  'How long the previous client secret remains valid after you rotate. Choose a preset duration from the list or immediately to invalidate the old secret at once. During the grace period, both secrets are accepted so callers can update without downtime.'
