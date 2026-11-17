/** Converts internal 24-hour "HH:MM" to the string PatternFly TimePicker expects in 12-hour mode. */
export function to12HourTimeString(hhmm: string): string {
  const [hourStr, minuteStr] = hhmm.split(':')
  const hour = Number(hourStr)
  if (hhmm === '' || minuteStr === undefined || Number.isNaN(hour)) {
    return hhmm
  }
  const suffix = hour >= 12 ? 'PM' : 'AM'
  const displayHour = hour % 12 === 0 ? 12 : hour % 12
  return `${displayHour}:${minuteStr} ${suffix}`
}
