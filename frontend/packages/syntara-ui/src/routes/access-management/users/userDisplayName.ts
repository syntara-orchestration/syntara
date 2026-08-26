export function userDisplayName(user: {
  first_name?: string | null
  last_name?: string | null
  username: string
}): string {
  return (
    [user.first_name, user.last_name]
      .map((part) => part?.trim())
      .filter(Boolean)
      .join(' ') || user.username
  )
}
