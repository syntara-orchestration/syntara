import { Content, ContentVariants, Timestamp } from '@patternfly/react-core'

import { toDisplayDate } from '../../utils/dateUtils'

/**
 * Displays a formatted date/time via PatternFly's Timestamp component
 * (e.g. "Jan 15, 2026, 2:30:45 PM"), or "-" if the date is invalid.
 */
export function DateCell(props: Readonly<{ dateString?: string | null }>) {
  const date = toDisplayDate(props.dateString)
  return (
    <Content component={ContentVariants.p}>
      {date ? <Timestamp date={date} dateFormat="medium" timeFormat="medium" /> : '-'}
    </Content>
  )
}
