/** Help popover body text for user create/edit form fields. */

export const USERNAME_HELP =
  'Unique sign-in identifier. Usernames are normalized to lowercase for local login. Federated users get username from preferred_username (or email prefix) at first IdP sign-in.'

export const EMAIL_HELP = 'Contact email address for this user.'

export const EMAIL_FEDERATED_EDIT_HELP =
  'Contact email for this user. It was set from the identity provider at first sign-in. You can change it here; it is not updated automatically on later logins.'

export const GROUPS_HELP =
  'Groups organize users for role assignments. Permissions flow from group memberships through assigned roles. New local users are added to the users group by default unless you choose otherwise.'

export const GROUPS_AUTHENTICATED_HINT = 'All users are automatically members of the authenticated group.'

export const STATUS_HELP =
  'When disabled, the user cannot sign in. Disabling revokes all refresh sessions and increments token_version so existing access tokens are rejected.'
