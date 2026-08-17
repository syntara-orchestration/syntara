import { Timestamp } from '@patternfly/react-core'
import type { CredentialsAPI } from '@syntara/contracts'

import { getUserDetailPath } from '../../routes/access-management/accessManagementPaths'
import { toDisplayDate } from '../../utils/dateUtils'
import { NxLink } from '../NxLink'

import styles from './UserTimestamp.module.css'

type UserReference = CredentialsAPI.components['schemas']['UserReference']

type UserTimestampProps = {
  user?: UserReference | string | null
  timestamp?: string
  /** Use subtle color for the timestamp (default: true). Set false for neutral color. */
  subtleTimestamp?: boolean
  /** Render user and date on a single line (default: false). Use true for table columns. */
  inline?: boolean
}

function resolveDisplayName(user: UserReference | string | null | undefined): string | undefined {
  if (!user) return undefined
  if (typeof user === 'string') return user
  return user.name
}

function resolveUserId(user: UserReference | string | null | undefined): string | undefined {
  if (!user || typeof user === 'string') return undefined
  return user.id
}

/**
 * Displays a formatted timestamp with an optional username.
 * When the user is a UserReference (has an id), the username renders as a link
 * to the user detail page. Plain strings render as brand-colored text.
 * In inline mode (tables): "date by username" on one line.
 * In stacked mode (detail views): date above "by username" on separate lines.
 */
export function UserTimestamp({
  user,
  timestamp,
  subtleTimestamp = true,
  inline = false,
}: Readonly<UserTimestampProps>) {
  const displayName = resolveDisplayName(user)
  const userId = resolveUserId(user)
  const date = toDisplayDate(timestamp)
  const formattedDate = date ? <Timestamp date={date} dateFormat="medium" timeFormat="medium" /> : '-'

  const userLink = userId ? (
    <NxLink to={getUserDetailPath(userId)}>{displayName}</NxLink>
  ) : (
    <span className={styles.userName}>{displayName}</span>
  )

  if (inline) {
    return (
      <span className={styles.inlineWrapper}>
        <span className={subtleTimestamp ? styles.inlineTimestampSubtle : undefined}>{formattedDate}</span>
        {displayName && <> by {userLink}</>}
      </span>
    )
  }

  return (
    <div className={styles.stackedWrapper}>
      <div className={subtleTimestamp ? styles.stackedTimestampSubtle : undefined}>{formattedDate}</div>
      {displayName && <div>by {userLink}</div>}
    </div>
  )
}
