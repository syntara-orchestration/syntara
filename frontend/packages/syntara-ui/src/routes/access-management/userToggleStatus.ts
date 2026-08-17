import { BUILTIN_ADMIN_TOGGLE_DISABLED_REASON, LAST_ADMIN_TOGGLE_DISABLED_REASON } from './adminConstants'

export type ToggleStatusResult = {
  canToggleStatus: boolean
  statusToggleDisabledReason: string | undefined
}

/**
 * Whether a user's enabled switch may be changed, and the tooltip when it may not.
 *
 * Builtin admin: can only be disabled by self, and only when other admins exist.
 * Other admin users: can be disabled by anyone, but not if they are the last admin.
 * Non-admin users: always toggleable (permission gating is separate).
 */
export function computeToggleStatus(
  isBuiltinUser: boolean,
  isEnabled: boolean,
  isSelf: boolean,
  isLastAdmin: boolean
): ToggleStatusResult {
  const canToggleStatus = isBuiltinUser ? !isEnabled || (isSelf && !isLastAdmin) : !isLastAdmin
  let statusToggleDisabledReason: string | undefined
  if (canToggleStatus) {
    statusToggleDisabledReason = undefined
  } else if (isBuiltinUser) {
    statusToggleDisabledReason = BUILTIN_ADMIN_TOGGLE_DISABLED_REASON
  } else {
    statusToggleDisabledReason = LAST_ADMIN_TOGGLE_DISABLED_REASON
  }
  return { canToggleStatus, statusToggleDisabledReason }
}
